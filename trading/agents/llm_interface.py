"""
LLM Interface for Strategy Generation

Abstract interface supporting multiple LLM backends:
- OpenAI GPT-4
- Anthropic Claude  
- Local models (via transformers)
- Mock/Rule-based fallback
"""

import json
import os
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class StrategyIntent:
    """Parsed from natural language input"""
    action: str = "buy"  # "buy", "sell", "hold"
    asset: Optional[str] = None  # "EURUSD", "BTCUSD", etc.
    timeframe: Optional[str] = None  # "1h", "4h", "daily"
    entry_conditions: List[str] = None
    exit_conditions: List[str] = None
    risk_constraints: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    raw_input: str = ""
    
    def __post_init__(self):
        if self.entry_conditions is None:
            self.entry_conditions = []
        if self.exit_conditions is None:
            self.exit_conditions = []
        if self.risk_constraints is None:
            self.risk_constraints = {}
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        return {
            'action': self.action,
            'asset': self.asset,
            'timeframe': self.timeframe,
            'entry_conditions': self.entry_conditions,
            'exit_conditions': self.exit_conditions,
            'risk_constraints': self.risk_constraints,
            'metadata': self.metadata,
            'raw_input': self.raw_input
        }


@dataclass
class StrategyProposal:
    """Generated strategy with executable parameters"""
    intent: StrategyIntent
    parameters: Dict[str, Any]
    confidence: float
    reasoning: str
    operators_emphasized: List[str]
    trajectory_filters: Dict[str, Any]
    validation_required: bool = True
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        return {
            'intent': self.intent.to_dict(),
            'parameters': self.parameters,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'operators_emphasized': self.operators_emphasized,
            'trajectory_filters': self.trajectory_filters,
            'validation_required': self.validation_required,
            'metadata': self.metadata
        }


class LLMStrategyInterface(ABC):
    """Abstract interface for LLM strategy generation"""
    
    @abstractmethod
    def generate_strategy(
        self,
        market_description: str,
        strategy_intent: StrategyIntent,
        context: Optional[Dict] = None
    ) -> StrategyProposal:
        """
        Generate strategy using LLM.
        
        Args:
            market_description: Natural language market context
            strategy_intent: Parsed strategy intent
            context: Additional context (patterns, metrics, etc.)
        
        Returns:
            StrategyProposal with executable parameters
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if LLM backend is available"""
        pass


class OpenAILLMInterface(LLMStrategyInterface):
    """OpenAI GPT-4 based strategy generation"""
    
    def __init__(
        self,
        model: str = "gpt-4",
        temperature: float = 0.2,
        max_tokens: int = 2000,
        api_key: Optional[str] = None
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self._client = None
        
        if self.api_key:
            try:
                import openai
                self._client = openai.OpenAI(api_key=self.api_key)
                logger.info(f"OpenAI interface initialized with model: {model}")
            except ImportError:
                logger.warning("openai package not installed")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI: {e}")
    
    def is_available(self) -> bool:
        return self._client is not None
    
    def generate_strategy(
        self,
        market_description: str,
        strategy_intent: StrategyIntent,
        context: Optional[Dict] = None
    ) -> StrategyProposal:
        """Generate strategy using OpenAI GPT"""
        if not self.is_available():
            raise RuntimeError("OpenAI client not available")
        
        prompt = self._build_prompt(market_description, strategy_intent, context)
        
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            parsed = json.loads(content)
            
            return self._parse_proposal(parsed, strategy_intent)
            
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            raise
    
    def _get_system_prompt(self) -> str:
        return """You are an expert ICT/SMC (Inner Circle Trader/Smart Money Concepts) quantitative trading strategist.

Your expertise includes:
- Order Blocks (OB) and Breaker Blocks
- Fair Value Gaps (FVG) 
- Liquidity sweeps and inducement
- Change of Character (ChoCH) and Break of Structure (BOS)
- Optimal Trade Entry (OTE) and Fibonacci confluence
- Market structure analysis and price delivery

You generate precise, executable trading strategies with specific price levels and clear risk management."""
    
    def _build_prompt(
        self,
        market_description: str,
        intent: StrategyIntent,
        context: Optional[Dict]
    ) -> str:
        """Build the strategy generation prompt"""
        
        context_str = ""
        if context:
            patterns = context.get('patterns', [])
            if patterns:
                context_str += f"\nDetected Patterns: {', '.join(p['type'] for p in patterns[:5])}"
            
            metrics = context.get('metrics', {})
            if metrics:
                context_str += f"\nVolatility: {metrics.get('volatility', 'N/A')}"
                context_str += f"\nTrend: {metrics.get('trend', 'N/A')}"
        
        prompt = f"""## Market Context
{market_description}{context_str}

## Strategy Intent
Action: {intent.action.upper()}
Asset: {intent.asset or 'Unspecified'}
Timeframe: {intent.timeframe or 'Unspecified'}
User Input: "{intent.raw_input}"

Entry Conditions: {', '.join(intent.entry_conditions) if intent.entry_conditions else 'Not specified'}
Exit Conditions: {', '.join(intent.exit_conditions) if intent.exit_conditions else 'Not specified'}
Risk Constraints: Max loss {intent.risk_constraints.get('max_loss', '1%')}, Position size {intent.risk_constraints.get('position_size', '1%')}

## Your Task
Generate a specific, executable trading strategy following ICT/SMC principles:

1. **Entry Logic**: What exact conditions trigger entry?
   - Price levels (specific numbers)
   - Pattern confirmations  
   - Timing considerations

2. **Exit Logic**: How to manage the trade?
   - Take profit targets (specific prices)
   - Stop loss level (specific price)
   - Trailing stop rules

3. **Risk Management**:
   - Position size (% of account)
   - Max risk per trade
   - R:R ratio

4. **Rationale**:
   - Why this strategy fits current conditions
   - Key ICT concepts applied
   - Risk/reward assessment

## Output Format
Return a JSON object with these exact fields:
{{
    "entry_price": float or null,
    "stop_loss": float or null,
    "take_profit": [float] or null,
    "position_size": float (percentage 0.0-1.0),
    "entry_conditions": [str],
    "exit_conditions": [str],
    "rationale": str (2-3 sentences explaining the strategy),
    "confidence": float (0.0-1.0),
    "operators_emphasized": [str] (list of operators like "order_block", "fvg", "liquidity_sweep"),
    "timeframe": str,
    "validation_notes": str (any warnings or conditions to verify)
}}"""
        return prompt
    
    def _parse_proposal(
        self,
        parsed: Dict,
        intent: StrategyIntent
    ) -> StrategyProposal:
        """Parse LLM output into StrategyProposal"""
        
        parameters = {
            'entry_price': parsed.get('entry_price'),
            'stop_loss': parsed.get('stop_loss'),
            'take_profit': parsed.get('take_profit'),
            'position_size': parsed.get('position_size', 0.01),
            'entry_conditions': parsed.get('entry_conditions', []),
            'exit_conditions': parsed.get('exit_conditions', [])
        }
        
        # Build trajectory filters from strategy
        trajectory_filters = {
            'min_energy': 0.3,
            'preferred_operators': parsed.get('operators_emphasized', [])
        }
        
        return StrategyProposal(
            intent=intent,
            parameters=parameters,
            confidence=parsed.get('confidence', 0.5),
            reasoning=parsed.get('rationale', 'No rationale provided'),
            operators_emphasized=parsed.get('operators_emphasized', []),
            trajectory_filters=trajectory_filters,
            validation_required=True,
            metadata={
                'validation_notes': parsed.get('validation_notes', ''),
                'timeframe': parsed.get('timeframe', intent.timeframe)
            }
        )


class MockLLMInterface(LLMStrategyInterface):
    """
    Mock LLM for testing and fallback.
    
    Generates rule-based strategies without API calls.
    """
    
    def __init__(self):
        logger.info("Mock LLM interface initialized")
    
    def is_available(self) -> bool:
        return True  # Always available
    
    def generate_strategy(
        self,
        market_description: str,
        strategy_intent: StrategyIntent,
        context: Optional[Dict] = None
    ) -> StrategyProposal:
        """Generate mock strategy based on rules"""
        
        # Extract current price from market description or context
        current_price = self._extract_price(market_description, context)
        
        # Generate strategy based on intent
        if strategy_intent.action == "buy":
            entry = current_price * 0.995 if current_price else 1.0  # Slight discount
            stop = entry * 0.99 if entry else 0.99
            targets = [entry * 1.01, entry * 1.02] if entry else [1.01, 1.02]
            operators = ["order_block", "fvg", "ote"]
            rationale = "Bullish setup with pullback entry targeting recent resistance."
        elif strategy_intent.action == "sell":
            entry = current_price * 1.005 if current_price else 1.0  # Slight premium
            stop = entry * 1.01 if entry else 1.01
            targets = [entry * 0.99, entry * 0.98] if entry else [0.99, 0.98]
            operators = ["order_block", "fvg", "breaker"]
            rationale = "Bearish setup with pullback entry targeting recent support."
        else:
            entry = None
            stop = None
            targets = None
            operators = []
            rationale = "No trade recommended based on current conditions."
        
        parameters = {
            'entry_price': entry,
            'stop_loss': stop,
            'take_profit': targets,
            'position_size': 0.01,
            'entry_conditions': ["Price reaches entry level", "Pattern confirmation"],
            'exit_conditions': ["Target reached", "Stop loss hit", "Invalidation"]
        }
        
        return StrategyProposal(
            intent=strategy_intent,
            parameters=parameters,
            confidence=0.6,
            reasoning=rationale,
            operators_emphasized=operators,
            trajectory_filters={'min_energy': 0.3, 'preferred_operators': operators},
            validation_required=True,
            metadata={'source': 'mock_llm', 'note': 'Rule-based fallback strategy'}
        )
    
    def _extract_price(self, description: str, context: Optional[Dict]) -> Optional[float]:
        """Extract current price from description or context"""
        # Try to find price in context
        if context:
            price = context.get('current_price')
            if price:
                return float(price)
        
        # Try to parse from description
        import re
        matches = re.findall(r'price[:\s]+(\d+\.?\d*)', description.lower())
        if matches:
            return float(matches[0])
        
        # Default
        return 1.0850  # Typical EURUSD price


class LLMInterfaceFactory:
    """Factory for creating LLM interfaces"""
    
    @staticmethod
    def create_interface(
        provider: str = "auto",
        **kwargs
    ) -> LLMStrategyInterface:
        """
        Create LLM interface based on provider.
        
        Args:
            provider: "openai", "anthropic", "mock", or "auto"
            **kwargs: Provider-specific arguments
        
        Returns:
            LLMStrategyInterface instance
        """
        if provider == "auto":
            # Try real LLMs first, fall back to mock
            openai_interface = OpenAILLMInterface(**kwargs)
            if openai_interface.is_available():
                return openai_interface
            
            logger.info("No real LLM available, using mock")
            return MockLLMInterface()
        
        elif provider == "openai":
            return OpenAILLMInterface(**kwargs)
        
        elif provider == "mock":
            return MockLLMInterface()
        
        else:
            raise ValueError(f"Unknown provider: {provider}")


def get_default_interface() -> LLMStrategyInterface:
    """Get default LLM interface (auto-detect)"""
    return LLMInterfaceFactory.create_interface("auto")
