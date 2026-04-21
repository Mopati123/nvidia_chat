"""
learning package - Backward-law weight adaptation.

Implements the learning mechanism that updates action functional
weights based on PnL, entropy reduction, and reconciliation status.

This closes the loop: experience → modifies action → modifies
interference → modifies future selection.
"""

from .weight_update_operator import WeightUpdateOperator, WeightUpdateResult

__all__ = [
    'WeightUpdateOperator',
    'WeightUpdateResult',
]
