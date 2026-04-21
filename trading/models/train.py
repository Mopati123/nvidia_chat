"""
Training Pipeline for Price Predictor

Supports 3-stage training:
1. Synthetic data (for initial validation)
2. Historical data (from Yahoo Finance)
3. Live data (from shadow trades)

First Principles:
- Train on synthetic first to validate architecture
- Gradual complexity increase (synthetic -> historical -> live)
- Conservative loss function with uncertainty calibration
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import logging
from tqdm import tqdm

logger = logging.getLogger(__name__)


class SyntheticDataset(Dataset):
    """Generate synthetic OHLCV sequences for initial training"""
    
    def __init__(self, n_samples: int = 10000, seq_len: int = 100, pred_len: int = 10):
        self.n_samples = n_samples
        self.seq_len = seq_len
        self.pred_len = pred_len
        
    def __len__(self):
        return self.n_samples
    
    def __getitem__(self, idx):
        """Generate one synthetic sample"""
        # Random walk with drift
        base_price = np.random.uniform(0.5, 2.0)
        drift = np.random.uniform(-0.0001, 0.0001)
        volatility = np.random.uniform(0.001, 0.01)
        
        prices = [base_price]
        for _ in range(self.seq_len + self.pred_len):
            change = np.random.normal(drift, volatility)
            prices.append(prices[-1] * (1 + change))
        
        prices = np.array(prices)
        
        # Create OHLCV from prices
        ohlcv = []
        for i in range(len(prices) - 1):
            close = prices[i]
            open_p = prices[max(0, i-1)]
            high = max(open_p, close) * (1 + abs(np.random.normal(0, 0.0005)))
            low = min(open_p, close) * (1 - abs(np.random.normal(0, 0.0005)))
            volume = np.random.randint(1000, 10000)
            
            ohlcv.append([open_p, high, low, close, volume])
        
        ohlcv = np.array(ohlcv)
        
        # Normalize by last close
        last_close = ohlcv[self.seq_len - 1, 3]
        ohlcv_normalized = ohlcv / last_close - 1.0
        
        # Generate operator scores (random for synthetic)
        operators = np.random.randn(self.seq_len, 18) * 0.1 + 0.5
        
        # Combine features
        x = np.concatenate([ohlcv_normalized[:self.seq_len], operators], axis=1)
        
        # Target: future price changes
        future_closes = ohlcv[self.seq_len:, 3]
        y_mean = (future_closes / last_close - 1.0)[:self.pred_len]
        
        # Target std (synthetic uncertainty)
        y_std = np.ones(self.pred_len) * 0.01
        
        # Target trend (direction)
        y_trend = np.sign(y_mean)
        
        return (
            torch.FloatTensor(x),
            torch.FloatTensor(y_mean),
            torch.FloatTensor(y_std),
            torch.FloatTensor(y_trend)
        )


class PricePredictorTrainer:
    """
    Training manager for PricePredictor.
    
    Handles data loading, training loop, validation, and checkpointing.
    """
    
    def __init__(self,
                 model: nn.Module,
                 device: str = "auto",
                 learning_rate: float = 1e-4,
                 weight_decay: float = 1e-5):
        self.device = self._get_device(device)
        self.model = model.to(self.device)
        
        self.optimizer = optim.AdamW(
            self.model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay
        )
        
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer, mode='min', factor=0.5, patience=5
        )
        
        self.train_losses = []
        self.val_losses = []
        
        logger.info(f"Trainer initialized on {self.device}")
    
    def _get_device(self, device: str) -> torch.device:
        """Auto-detect best available device"""
        if device == "auto":
            if torch.cuda.is_available():
                return torch.device("cuda")
            elif torch.backends.mps.is_available():
                return torch.device("mps")
            else:
                return torch.device("cpu")
        return torch.device(device)
    
    def loss_function(self,
                     pred_mean: torch.Tensor,
                     pred_std: torch.Tensor,
                     pred_trend: torch.Tensor,
                     target_mean: torch.Tensor,
                     target_std: torch.Tensor,
                     target_trend: torch.Tensor) -> torch.Tensor:
        """
        Combined loss function.
        
        Components:
        - MSE on mean prediction
        - KL divergence on std (calibration)
        - BCE on trend direction
        """
        # Mean prediction loss
        mse_loss = F.mse_loss(pred_mean, target_mean)
        
        # Uncertainty calibration loss
        # Penalize when predicted std doesn't match actual error
        actual_error = torch.abs(pred_mean.detach() - target_mean)
        std_loss = F.mse_loss(pred_std, actual_error)
        
        # Trend direction loss
        trend_loss = F.mse_loss(pred_trend, target_trend)
        
        # Combined
        total_loss = mse_loss + 0.1 * std_loss + 0.5 * trend_loss
        
        return total_loss
    
    def train_epoch(self, dataloader: DataLoader) -> float:
        """Train for one epoch"""
        self.model.train()
        total_loss = 0.0
        n_batches = 0
        
        for batch in tqdm(dataloader, desc="Training"):
            x, y_mean, y_std, y_trend = batch
            x = x.to(self.device)
            y_mean = y_mean.to(self.device)
            y_std = y_std.to(self.device)
            y_trend = y_trend.to(self.device)
            
            # Forward
            pred_mean, pred_std, pred_trend = self.model(x)
            
            # Loss
            loss = self.loss_function(
                pred_mean, pred_std, pred_trend,
                y_mean, y_std, y_trend
            )
            
            # Backward
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimizer.step()
            
            total_loss += loss.item()
            n_batches += 1
        
        return total_loss / n_batches if n_batches > 0 else 0.0
    
    def validate(self, dataloader: DataLoader) -> Dict[str, float]:
        """Validate on validation set"""
        self.model.eval()
        total_loss = 0.0
        total_mae = 0.0
        n_batches = 0
        
        with torch.no_grad():
            for batch in tqdm(dataloader, desc="Validation"):
                x, y_mean, y_std, y_trend = batch
                x = x.to(self.device)
                y_mean = y_mean.to(self.device)
                y_std = y_std.to(self.device)
                y_trend = y_trend.to(self.device)
                
                # Forward
                pred_mean, pred_std, pred_trend = self.model(x)
                
                # Loss
                loss = self.loss_function(
                    pred_mean, pred_std, pred_trend,
                    y_mean, y_std, y_trend
                )
                
                # MAE
                mae = torch.abs(pred_mean - y_mean).mean()
                
                total_loss += loss.item()
                total_mae += mae.item()
                n_batches += 1
        
        return {
            'loss': total_loss / n_batches if n_batches > 0 else 0.0,
            'mae': total_mae / n_batches if n_batches > 0 else 0.0
        }
    
    def train(self,
             train_dataloader: DataLoader,
             val_dataloader: Optional[DataLoader] = None,
             epochs: int = 100,
             save_dir: Optional[str] = None,
             early_stopping_patience: int = 10) -> Dict:
        """
        Full training loop.
        
        Args:
            train_dataloader: Training data
            val_dataloader: Validation data (optional)
            epochs: Number of epochs
            save_dir: Directory to save checkpoints
            early_stopping_patience: Epochs to wait before stopping
        
        Returns:
            Training history
        """
        best_val_loss = float('inf')
        patience_counter = 0
        
        for epoch in range(epochs):
            logger.info(f"\nEpoch {epoch + 1}/{epochs}")
            
            # Train
            train_loss = self.train_epoch(train_dataloader)
            self.train_losses.append(train_loss)
            logger.info(f"Train loss: {train_loss:.6f}")
            
            # Validate
            if val_dataloader:
                val_metrics = self.validate(val_dataloader)
                val_loss = val_metrics['loss']
                self.val_losses.append(val_loss)
                logger.info(f"Val loss: {val_loss:.6f}, MAE: {val_metrics['mae']:.6f}")
                
                # Learning rate scheduling
                self.scheduler.step(val_loss)
                
                # Early stopping
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                    
                    # Save best model
                    if save_dir:
                        self.save_checkpoint(save_dir, f"best_model.pt")
                else:
                    patience_counter += 1
                    if patience_counter >= early_stopping_patience:
                        logger.info(f"Early stopping after {epoch + 1} epochs")
                        break
            
            # Save checkpoint every 10 epochs
            if save_dir and (epoch + 1) % 10 == 0:
                self.save_checkpoint(save_dir, f"checkpoint_epoch_{epoch + 1}.pt")
        
        return {
            'train_losses': self.train_losses,
            'val_losses': self.val_losses,
            'best_val_loss': best_val_loss,
            'epochs_trained': len(self.train_losses)
        }
    
    def save_checkpoint(self, save_dir: str, filename: str):
        """Save model checkpoint"""
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        
        checkpoint = {
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'train_losses': self.train_losses,
            'val_losses': self.val_losses
        }
        
        torch.save(checkpoint, save_path / filename)
        logger.info(f"Saved checkpoint: {save_path / filename}")


def train_synthetic(model_dir: str = "models/price_predictor",
                   epochs: int = 50,
                   batch_size: int = 32) -> PricePredictorTrainer:
    """
    Train on synthetic data.
    
    This is Stage 1 training - validates the architecture works
    before moving to real data.
    
    Args:
        model_dir: Directory to save models
        epochs: Number of training epochs
        batch_size: Batch size
    
    Returns:
        Trained model
    """
    from .price_predictor import PricePredictor
    
    logger.info("="*70)
    logger.info("STAGE 1: Training on Synthetic Data")
    logger.info("="*70)
    
    # Create datasets
    train_dataset = SyntheticDataset(n_samples=10000)
    val_dataset = SyntheticDataset(n_samples=2000)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size)
    
    # Create model and trainer
    model = PricePredictor()
    trainer = PricePredictorTrainer(model)
    
    # Train
    history = trainer.train(
        train_loader,
        val_loader,
        epochs=epochs,
        save_dir=model_dir,
        early_stopping_patience=10
    )
    
    logger.info("\n" + "="*70)
    logger.info("Stage 1 Complete!")
    logger.info(f"Best val loss: {history['best_val_loss']:.6f}")
    logger.info(f"Epochs trained: {history['epochs_trained']}")
    logger.info("="*70)
    
    return trainer


if __name__ == "__main__":
    # Train on synthetic data
    trainer = train_synthetic()
    print("Training complete!")
