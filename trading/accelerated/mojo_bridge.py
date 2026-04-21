"""
mojo_bridge.py — Python bridge to Mojo engine

Enables calling Mojo from Python until direct interop is available.
"""

import subprocess
import json
import os
import logging
from typing import Dict, List, Optional, Any
import numpy as np

logger = logging.getLogger(__name__)

MOJO_AVAILABLE = False
MOJO_BINARY_PATH = None

def check_mojo_available() -> bool:
    """Check if Mojo compiler and runtime are available"""
    global MOJO_AVAILABLE, MOJO_BINARY_PATH
    
    try:
        # Check if mojo command is available
        result = subprocess.run(
            ['mojo', '--version'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"✓ Mojo available: {result.stdout.strip()}")
            
            # Check for pre-built binary
            binary_path = os.path.join(
                os.path.dirname(__file__),
                'mojo', 'core', 'trajectory_engine'
            )
            
            if os.path.exists(binary_path):
                MOJO_BINARY_PATH = binary_path
                MOJO_AVAILABLE = True
                logger.info(f"✓ Mojo binary found: {binary_path}")
            else:
                logger.warning("⚠ Mojo binary not built. Run: mojo build trajectory_engine.mojo")
            
            return MOJO_AVAILABLE
    except FileNotFoundError:
        logger.debug("Mojo not installed")
    
    return False


class MojoEngineBridge:
    """
    Bridge to Mojo-accelerated engine.
    
    Falls back to Cython or NumPy if Mojo unavailable.
    """
    
    def __init__(self):
        self.available = check_mojo_available()
        self.binary_path = MOJO_BINARY_PATH
    
    def generate_trajectories(
        self,
        initial_price: float,
        initial_velocity: float,
        potential_force: float,
        n_trajectories: int = 100,
        n_steps: int = 50,
        epsilon: float = 0.015
    ) -> Optional[Dict]:
        """
        Call Mojo engine to generate trajectories.
        
        Returns trajectory data or None if failed.
        """
        if not self.available:
            return None
        
        try:
            # Prepare input data
            input_data = {
                'initial_price': initial_price,
                'initial_velocity': initial_velocity,
                'potential_force': potential_force,
                'n_trajectories': n_trajectories,
                'n_steps': n_steps,
                'epsilon': epsilon
            }
            
            # Write to temp file
            temp_input = '/tmp/mojo_input.json'
            temp_output = '/tmp/mojo_output.json'
            
            with open(temp_input, 'w') as f:
                json.dump(input_data, f)
            
            # Run Mojo binary
            result = subprocess.run(
                [self.binary_path, temp_input, temp_output],
                capture_output=True,
                text=True,
                timeout=10  # 10 second timeout
            )
            
            if result.returncode != 0:
                logger.error(f"Mojo execution failed: {result.stderr}")
                return None
            
            # Read output
            with open(temp_output, 'r') as f:
                output = json.load(f)
            
            return output
            
        except Exception as e:
            logger.error(f"Mojo bridge error: {e}")
            return None
    
    def compute_operator_scores(
        self,
        prices: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray
    ) -> Optional[List[float]]:
        """Call Mojo to compute 18-operator scores"""
        if not self.available:
            return None
        
        try:
            # Convert arrays to lists for JSON serialization
            input_data = {
                'prices': prices.tolist(),
                'highs': highs.tolist(),
                'lows': lows.tolist(),
                'opens': opens.tolist(),
                'closes': closes.tolist(),
                'volumes': volumes.tolist()
            }
            
            temp_input = '/tmp/mojo_operators_input.json'
            temp_output = '/tmp/mojo_operators_output.json'
            
            with open(temp_input, 'w') as f:
                json.dump(input_data, f)
            
            # Run Mojo
            result = subprocess.run(
                [self.binary_path, '--operators', temp_input, temp_output],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None
            
            with open(temp_output, 'r') as f:
                output = json.load(f)
            
            return output.get('scores', [])
            
        except Exception as e:
            logger.error(f"Mojo operators error: {e}")
            return None


# Singleton
mojo_bridge = MojoEngineBridge()


def get_mojo_status() -> Dict:
    """Get Mojo availability status"""
    return {
        'available': MOJO_AVAILABLE,
        'binary_path': MOJO_BINARY_PATH,
        'version': '1.0.0' if MOJO_AVAILABLE else None
    }
