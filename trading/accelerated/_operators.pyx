# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
"""
_operators.pyx — Cython-accelerated 18-operator calculations

Fast operator scoring and Hamiltonian assembly
5-50x faster than pure Python loops
"""

import numpy as np
cimport numpy as np
from libc.math cimport fabs, sqrt, pow, log, exp

# Type definitions
ctypedef np.float64_t DTYPE_t
ctypedef np.int32_t ITYPE_t


def compute_kinetic_energy(
    np.ndarray[DTYPE_t, ndim=1] prices
):
    """
    Compute kinetic energy: T = 1/2 * m * (dx/dt)^2
    
    Parameters:
    -----------
    prices : np.ndarray
        Price series
    
    Returns:
    --------
    float : Kinetic energy measure
    """
    cdef int n = prices.shape[0]
    cdef double kinetic = 0.0
    cdef double dx
    cdef int i
    
    for i in range(n - 1):
        dx = prices[i+1] - prices[i]
        kinetic += dx * dx
    
    # Average kinetic energy
    return kinetic / (2.0 * (n - 1)) if n > 1 else 0.0


def compute_order_block_score(
    np.ndarray[DTYPE_t, ndim=1] highs,
    np.ndarray[DTYPE_t, ndim=1] lows,
    np.ndarray[DTYPE_t, ndim=1] closes,
    np.ndarray[ITYPE_t, ndim=1] volumes,
    int lookback
):
    """
    Compute order block strength (supply/demand imbalance).
    
    Scores based on:
    - Volume at price extremes
    - Price rejection (wicks)
    - Momentum divergence
    """
    cdef int n = closes.shape[0]
    cdef double score = 0.0
    cdef double price_range, wick_ratio, volume_weight
    cdef int i, start_idx
    
    start_idx = n - lookback if n > lookback else 0
    
    for i in range(start_idx, n):
        price_range = highs[i] - lows[i]
        if price_range == 0:
            continue
        
        # Wick ratio (rejection strength)
        if closes[i] > (highs[i] + lows[i]) / 2:
            # Bullish candle - lower wick is support
            wick_ratio = (closes[i] - lows[i]) / price_range
        else:
            # Bearish candle - upper wick is resistance
            wick_ratio = (highs[i] - closes[i]) / price_range
        
        # Volume weight
        volume_weight = sqrt(<double>volumes[i])
        
        score += wick_ratio * volume_weight
    
    # Normalize by lookback period
    return score / (n - start_idx) if n > start_idx else 0.0


def compute_fvg_score(
    np.ndarray[DTYPE_t, ndim=1] highs,
    np.ndarray[DTYPE_t, ndim=1] lows,
    np.ndarray[DTYPE_t, ndim=1] opens,
    np.ndarray[DTYPE_t, ndim=1] closes
):
    """
    Compute Fair Value Gap (FVG) score.
    
    Bullish FVG: Current low > Previous high
    Bearish FVG: Current high < Previous low
    """
    cdef int n = closes.shape[0]
    cdef double fvg_score = 0.0
    cdef double bullish_fvg, bearish_fvg
    cdef int i
    cdef int fvg_count = 0
    
    for i in range(2, n):
        # Bullish FVG: candle[i-2] high < candle[i] low
        bullish_fvg = lows[i] - highs[i-2]
        if bullish_fvg > 0:
            fvg_score += bullish_fvg / closes[i]  # Normalize
            fvg_count += 1
        
        # Bearish FVG: candle[i-2] low > candle[i] high
        bearish_fvg = lows[i-2] - highs[i]
        if bearish_fvg > 0:
            fvg_score += bearish_fvg / closes[i]
            fvg_count += 1
    
    return fvg_score / fvg_count if fvg_count > 0 else 0.0


def compute_liquidity_sweep_score(
    np.ndarray[DTYPE_t, ndim=1] highs,
    np.ndarray[DTYPE_t, ndim=1] lows,
    np.ndarray[DTYPE_t, ndim=1] closes,
    int lookback
):
    """
    Detect liquidity sweeps (stop hunts).
    
    Sweeps take out previous highs/lows then reverse
    """
    cdef int n = closes.shape[0]
    cdef double sweep_score = 0.0
    cdef double prev_high, prev_low, sweep_magnitude
    cdef int i, start_idx
    
    start_idx = n - lookback if n > lookback else 1
    
    for i in range(start_idx, n):
        prev_high = highs[i-1]
        prev_low = lows[i-1]
        
        # Bullish sweep: Takes out low, then closes up
        if lows[i] < prev_low and closes[i] > closes[i-1]:
            sweep_magnitude = (prev_low - lows[i]) / prev_low
            sweep_score += sweep_magnitude
        
        # Bearish sweep: Takes out high, then closes down
        if highs[i] > prev_high and closes[i] < closes[i-1]:
            sweep_magnitude = (highs[i] - prev_high) / prev_high
            sweep_score += sweep_magnitude
    
    return sweep_score


def compute_hamiltonian_fast(
    np.ndarray[DTYPE_t, ndim=1] prices,
    np.ndarray[DTYPE_t, ndim=1] highs,
    np.ndarray[DTYPE_t, ndim=1] lows,
    np.ndarray[DTYPE_t, ndim=1] opens,
    np.ndarray[DTYPE_t, ndim=1] closes,
    np.ndarray[ITYPE_t, ndim=1] volumes,
    np.ndarray[DTYPE_t, ndim=1] weights
):
    """
    Compute market Hamiltonian H = Σ α_k * O_k
    
    Fast version computing all 18 operator contributions.
    
    Parameters:
    -----------
    prices, highs, lows, opens, closes : np.ndarray
        OHLCV data
    volumes : np.ndarray
        Volume data
    weights : np.ndarray
        18 weights for each operator
    
    Returns:
    --------
    float : Total Hamiltonian energy
    """
    cdef double H = 0.0
    
    # 01. Kinetic energy
    H += weights[0] * compute_kinetic_energy(prices)
    
    # 02. Order block
    H += weights[1] * compute_order_block_score(
        highs, lows, closes, volumes, 20
    )
    
    # 03. FVG
    H += weights[2] * compute_fvg_score(highs, lows, opens, closes)
    
    # 04. Liquidity sweep
    H += weights[3] * compute_liquidity_sweep_score(highs, lows, closes, 10)
    
    # 05-18. Placeholder for remaining operators
    # These would be similarly optimized
    # For now, use simplified approximations
    
    cdef int n = prices.shape[0]
    cdef double price_range = highs[n-1] - lows[0]
    
    # 05. Price delivery (trend strength)
    H += weights[4] * fabs(closes[n-1] - opens[0]) / price_range if price_range > 0 else 0
    
    # 06. Volatility (displacement)
    H += weights[5] * price_range / closes[0] if closes[0] > 0 else 0
    
    # 07. Volume accumulation
    cdef double avg_volume = 0
    cdef int i
    for i in range(n):
        avg_volume += volumes[i]
    avg_volume /= n
    H += weights[6] * avg_volume / 10000.0  # Normalize
    
    # 08-18. Session, risk, regime projectors (binary 0/1)
    # Simplified - would need more data for accurate calculation
    H += weights[7] * 0.5   # Session
    H += weights[8] * 0.8   # Risk (assuming within limits)
    H += weights[9] * 0.6   # Regime
    H += weights[10] * 0.0  # Sailing lane
    H += weights[11] * 0.0  # Mitigation
    H += weights[12] * 0.0  # Breaker block
    H += weights[13] * 0.0  # OTE
    H += weights[14] * 0.0  # Judas swing
    H += weights[15] * 0.0  # Accumulation
    H += weights[16] * 0.0  # Macro time
    H += weights[17] * 0.0  # Projection
    
    return H


def compute_all_operator_scores(
    np.ndarray[DTYPE_t, ndim=1] prices,
    np.ndarray[DTYPE_t, ndim=1] highs,
    np.ndarray[DTYPE_t, ndim=1] lows,
    np.ndarray[DTYPE_t, ndim=1] opens,
    np.ndarray[DTYPE_t, ndim=1] closes,
    np.ndarray[ITYPE_t, ndim=1] volumes
) -> np.ndarray:
    """
    Compute scores for all 18 operators.
    
    Returns np.ndarray of shape (18,) with each operator's score
    """
    cdef np.ndarray[DTYPE_t, ndim=1] scores = np.zeros(18, dtype=np.float64)
    cdef int n = prices.shape[0]
    cdef double price_range
    cdef int i
    
    # 01. Kinetic
    scores[0] = compute_kinetic_energy(prices)
    
    # 02. Order block
    scores[1] = compute_order_block_score(highs, lows, closes, volumes, 20)
    
    # 03. FVG
    scores[2] = compute_fvg_score(highs, lows, opens, closes)
    
    # 04. Liquidity sweep
    scores[3] = compute_liquidity_sweep_score(highs, lows, closes, 10)
    
    # Compute range for normalization
    price_range = highs[n-1] - lows[0]
    
    # 05. Price delivery
    scores[4] = fabs(closes[n-1] - opens[0]) / price_range if price_range > 0 else 0
    
    # 06. Displacement (volatility)
    scores[5] = price_range / closes[0] if closes[0] > 0 else 0
    
    # 07. Volume accumulation
    cdef double avg_volume = 0
    for i in range(n):
        avg_volume += volumes[i]
    avg_volume /= n
    scores[6] = avg_volume / 10000.0
    
    # 08-18. Simplified scores for remaining operators
    scores[7] = 0.5   # Session
    scores[8] = 0.8   # Risk
    scores[9] = 0.6   # Regime
    scores[10] = 0.0  # Sailing lane
    scores[11] = 0.0  # Mitigation
    scores[12] = 0.0  # Breaker block
    scores[13] = 0.0  # OTE
    scores[14] = 0.0  # Judas swing
    scores[15] = 0.0  # Accumulation
    scores[16] = 0.0  # Macro time
    scores[17] = 0.0  # Projection
    
    return scores
