# boat_ride/providers/waves_inland.py
from __future__ import annotations

from dataclasses import dataclass
from math import tanh
from typing import Optional, Tuple


def _ft_to_m(ft: float) -> float:
    return ft / 3.28084


def _m_to_ft(m: float) -> float:
    return m * 3.28084


def _kt_to_mps(kt: float) -> float:
    return kt * 0.514444


@dataclass(frozen=True)
class InlandWaveInputs:
    wind_kt: float
    fetch_nm: float
    depth_m: Optional[float] = None
    # later: wind_duration_hr, shoreline_exposure, etc.


def compute_inland_waves(inputs: InlandWaveInputs) -> Tuple[float, float]:
    """
    Lightweight SMB/JONSWAP-style growth with optional shallow-water limiting.
    Returns (wave_height_ft, wave_period_s).

    Goals:
      - stable period estimate (not just height)
      - reasonable caps for protected waters
      - optional depth limiting without heavy modeling

    This is still an approximation — but it’s *structured* like real wave growth models.
    """
    wind_kt = float(inputs.wind_kt or 0.0)
    fetch_nm = float(inputs.fetch_nm or 0.0)
    if wind_kt <= 0.0 or fetch_nm <= 0.0:
        return 0.0, 0.0

    # Clamp fetch to avoid absurd growth in “inland mode”
    fetch_nm = max(0.05, min(fetch_nm, 25.0))

    g = 9.81
    U = _kt_to_mps(wind_kt)
    F = fetch_nm * 1852.0  # nm -> m

    # Dimensionless fetch
    X = g * F / max(U * U, 1e-9)

    # SMB-ish / JONSWAP-ish growth curves (commonly used in simplified forecasting)
    # Hs = (U^2/g) * A * tanh(B * X^m)
    # Tp = (U/g)   * C * tanh(D * X^n)
    hs_m = (U * U / g) * 0.283 * tanh(0.0125 * (X ** 0.42))
    tp_s = (U / g) * 7.54 * tanh(0.077 * (X ** 0.25))

    # Shallow-water / depth limiting (very simple but helpful)
    # If depth is known and shallow, limit growth and period.
    d = inputs.depth_m
    if d is not None:
        try:
            d = float(d)
        except Exception:
            d = None
    if d is not None and d > 0:
        # cap Hs in shallow water (coarse engineering heuristic)
        # Hmax ≈ 0.6 * depth (meters)
        hs_cap = 0.6 * d
        hs_m = min(hs_m, hs_cap)

        # period also tends to be shorter in shallow constrained water
        # (gentle scaling; don’t crush it too hard)
        tp_s = tp_s * min(1.0, (d / 20.0) ** 0.25)

    # Convert to “protected water plausible” clamps
    hs_ft = _m_to_ft(hs_m)
    hs_ft = max(0.0, min(hs_ft, 6.0))
    tp_s = max(2.0 + 0.2 * fetch_nm, min(tp_s, 8.5))


    return float(hs_ft), float(tp_s)
