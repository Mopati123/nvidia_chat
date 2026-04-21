"""
trading/accelerated/ — Performance acceleration layer

Tiered acceleration: Cython → Numba → Pure Python
"""

import logging

logger = logging.getLogger(__name__)

# Cython availability flags
CYTHON_AVAILABLE = False
CYTHON_PATH_INTEGRAL = False
CYTHON_OPERATORS = False

try:
    from . import _path_integral
    CYTHON_PATH_INTEGRAL = True
    CYTHON_AVAILABLE = True
    logger.info("✓ Cython path integral module loaded")
except ImportError:
    logger.debug("Cython path integral not available")

try:
    from . import _operators
    CYTHON_OPERATORS = True
    CYTHON_AVAILABLE = True
    logger.info("✓ Cython operators module loaded")
except ImportError:
    logger.debug("Cython operators not available")

# Backend selection
def get_best_backend():
    """Return best available acceleration backend"""
    if CYTHON_AVAILABLE:
        return "cython"
    return "numpy"

__all__ = [
    'CYTHON_AVAILABLE',
    'CYTHON_PATH_INTEGRAL', 
    'CYTHON_OPERATORS',
    'get_best_backend'
]
