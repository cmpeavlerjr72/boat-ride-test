from __future__ import annotations

from math import tanh
from typing import Any, Dict, List, Optional

from boat_ride.core.models import BoatProfile, EnvAtPoint, RideScore


def _deepwater_wavelength_m(period_s: float) -> Optional[float]:
    """
    Deep-water approximation: L = g T^2 / (2π)
    Good enough for a steepness proxy for ride-quality scoring.
    """
    if period_s <= 0:
        return None
    g = 9.81
    return (g * (period_s ** 2)) / (2.0 * 3.141592653589793)


def _angle_diff_deg(a: float, b: float) -> float:
    """Minimal circular difference in degrees in [0, 180]."""
    d = (a - b) % 360.0
    if d > 180.0:
        d = 360.0 - d
    return float(d)

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _wrap360(d: float) -> float:
    return float(d % 360.0)


def _tide_flow_dir_est(route_heading_deg: Optional[float], tide_phase: Optional[str]) -> Optional[float]:
    """
    Estimate tidal flow direction (deg CW from north) using route heading as a proxy for channel axis.
      flood => along route heading
      ebb   => opposite route heading
      slack/unknown => None
    """
    if route_heading_deg is None or not tide_phase:
        return None
    tp = str(tide_phase).strip().lower()
    if tp == "flood":
        return _wrap360(route_heading_deg)
    if tp == "ebb":
        return _wrap360(route_heading_deg + 180.0)
    return None


def _tide_wind_opposition_penalty(
    *,
    wind_kt: float,
    wind_dir_deg: Optional[float],
    tide_rate_ft_per_hr: Optional[float],
    tide_phase: Optional[str],
    route_heading_deg: Optional[float],
    fetch_nm: Optional[float],
) -> Optional[tuple[float, str]]:
    """
    Small, gated add-on penalty for wind opposing estimated tidal flow direction.

    - Smooth wind scaling (no hard 8 kt gate)
    - Tide-rate window scaling
    - Emphasize near-opposition; ignore "cross-ish" cases
    """
    if wind_dir_deg is None or tide_rate_ft_per_hr is None:
        return None

    flow_dir = _tide_flow_dir_est(route_heading_deg, tide_phase)
    if flow_dir is None:
        return None

    rate = abs(float(tide_rate_ft_per_hr))

    # Tide-rate window: only meaningful current regimes participate
    TIDE_MIN = 1.0   # ft/hr
    TIDE_FULL = 3.0  # ft/hr
    if rate < TIDE_MIN:
        return None
    rate_factor = _clamp01((rate - TIDE_MIN) / max(1e-6, (TIDE_FULL - TIDE_MIN)))

    # Smooth wind scaling (noise floor + ramp)
    WIND_MIN = 3.0    # kt
    WIND_FULL = 15.0  # kt
    if wind_kt < WIND_MIN:
        return None
    wind_factor = _clamp01((wind_kt - WIND_MIN) / max(1e-6, (WIND_FULL - WIND_MIN)))

    # Keep out of offshore/open-water cases by default
    if fetch_nm is not None and float(fetch_nm) > 12.0:
        return None

    d = _angle_diff_deg(float(wind_dir_deg), float(flow_dir))  # 0 aligned, 180 opposed

    # IMPORTANT: don't trigger for cross-ish flow. Start only when it's genuinely "against".
    # Ramp from 135°..180° and square for emphasis near 180°.
    if d < 135.0:
        return None
    base = _clamp01((d - 135.0) / 45.0)
    angle_factor = base * base

    # Context factor: smaller fetch => more plausible wind-against-current chop
    if fetch_nm is None:
        context_factor = 1.0
    else:
        context_factor = _clamp01((12.0 - float(fetch_nm)) / 8.0)  # 1 at 4 nm, 0 at 12 nm

    MAXP = 4.0
    penalty = MAXP * angle_factor * rate_factor * wind_factor * context_factor
    if penalty <= 0:
        return None

    reason = f"Wind vs tide flow (est) (Δ={d:.0f}°)"
    return float(penalty), reason



def score_point(boat: BoatProfile, env: EnvAtPoint) -> RideScore:
    reasons: List[str] = []
    detail: Dict[str, Any] = {}

    wind = float(getattr(env, "wind_speed_kt", None) or 0.0)
    pop = float(getattr(env, "precip_prob", None) or 0.0)

    wave = getattr(env, "wave_height_ft", None)
    wave = float(wave) if wave is not None else 0.0

    wave_period = getattr(env, "wave_period_s", None)
    wave_period = float(wave_period) if wave_period is not None else None

    wave_dir = getattr(env, "wave_dir_deg", None)
    wave_dir = float(wave_dir) if wave_dir is not None else None

    wind_dir = getattr(env, "wind_dir_deg", None)
    wind_dir = float(wind_dir) if wind_dir is not None else None

    gust = getattr(env, "wind_gust_kt", None)
    gust = float(gust) if gust is not None else None

    meta = getattr(env, "meta", {}) or {}
    wave_source = meta.get("waves_source") or meta.get("wave_source") or "model/obs"

    # ---- Derived wave “shape” metrics ----
    steepness = None  # H/L
    if wave > 0 and wave_period is not None and wave_period > 0:
        L_m = _deepwater_wavelength_m(wave_period)
        if L_m and L_m > 0:
            H_m = wave / 3.28084
            steepness = float(H_m / L_m)

    # ---- Scoring (POC heuristic, upgraded) ----
    score = 100.0

    # Wind penalty (base)
    if wind > 0:
        wind_ratio = wind / max(1.0, boat.max_safe_wind_kt)
        score -= 35.0 * (wind_ratio ** 1.3)
        if wind_ratio > 1.0:
            reasons.append(f"Wind {wind:.0f} kt above comfort limit")

    # Gust penalty (optional)
    if gust is not None and gust > wind and gust > 0:
        gust_excess = gust - wind
        # Scale “excess gustiness” relative to boat’s wind limit
        gust_ratio = gust_excess / max(1.0, 0.35 * boat.max_safe_wind_kt)
        score -= 10.0 * (gust_ratio ** 1.2)
        if gust_excess >= 8:
            reasons.append(f"Gusty (+{gust_excess:.0f} kt)")

    # Wave height penalty (base)
    if wave > 0:
        wave_ratio = wave / max(0.5, boat.max_safe_wave_ft)
        score -= 50.0 * (wave_ratio ** 1.4)
        if wave_ratio > 1.0:
            reasons.append(f"Seas {wave:.1f} ft above comfort limit")

    # Short-period penalty (optional)
    if wave > 0 and wave_period is not None and wave_period > 0:
        # Comfortable: ~8–10s. Below ~6s becomes “punchy” quickly.
        if wave_period < 8.0:
            shortness = (8.0 - wave_period) / 4.0  # 4s -> 1.0, 8s -> 0
            score -= 12.0 * (shortness ** 1.4)
            if wave_period <= 6.0:
                reasons.append(f"Short period seas ({wave_period:.0f}s)")

    # Steepness penalty (optional)
    if steepness is not None:
        # Typical deep-water steepness: ~0.01 gentle; >0.03 steep
        if steepness > 0.02:
            s = (steepness - 0.02) / 0.02  # 0.04 => 1.0
            score -= 14.0 * (s ** 1.2)
            if steepness >= 0.03:
                reasons.append("Steep seas")

    # Wind opposing waves penalty (optional)
    if wind_dir is not None and wave_dir is not None and wind > 0 and wave > 0:
        # If wind is against wave direction, seas steepen / chop increases.
        d = _angle_diff_deg(wind_dir, wave_dir)  # 0 aligned, 180 opposed
        opposition = max(0.0, (d - 90.0) / 90.0)  # 0 until 90°, 1 at 180°
        score -= 10.0 * opposition * min(1.0, wind / max(1.0, boat.max_safe_wind_kt))
        if d >= 140:
            reasons.append("Wind against seas")

    # Tide-flow penalty (proxy for current strength)
    tide_rate = (env.meta or {}).get("tide_rate_ft_per_hr")
    if tide_rate is not None:
        rate = abs(float(tide_rate))

        # Below ~0.3 ft/hr: negligible
        # Around 1.0–1.5 ft/hr: noticeable turbulence in rivers/inlets
        if rate > 0.3:
            # Normalize: 0 at 0.3, 1 at ~1.5
            r = min(1.0, (rate - 0.3) / 1.2)
            score -= 8.0 * (r ** 1.3)

            if rate >= 1.0:
                reasons.append("Strong tidal flow")

            # Directional tide×wind interaction (wind-against-estimated-current chop)
            tw = _tide_wind_opposition_penalty(
                wind_kt=wind,
                wind_dir_deg=wind_dir,
                tide_rate_ft_per_hr=(env.meta or {}).get("tide_rate_ft_per_hr"),
                tide_phase=(env.meta or {}).get("tide_phase"),
                route_heading_deg=(env.meta or {}).get("route_heading_deg"),
                fetch_nm=(env.meta or {}).get("fetch_nm"),
            )
            if tw is not None:
                pen, why = tw
                score -= pen
                reasons.append(why)


    # Precip penalty
    if pop > 0:
        score -= 15.0 * pop
        if pop >= 0.6:
            reasons.append(f"High rain chance ({int(pop * 100)}%)")

    # Comfort bias tweak
    score += boat.comfort_bias * 8.0

    # Clamp
    score = max(0.0, min(100.0, score))

    # Label thresholds
    if score >= 80:
        label = "great"
    elif score >= 60:
        label = "ok"
    elif score >= 40:
        label = "rough"
    else:
        label = "avoid"

    # Detail for debugging & CLI display
    detail.update(
        {
            "wind_kt": wind,
            "wind_gust_kt": gust,
            "wind_dir_deg": wind_dir,
            "pop": pop,
            "wave_ft": wave,
            "wave_period_s": wave_period,
            "wave_dir_deg": wave_dir,
            "wave_steepness": steepness,
            "tide_ft": env.tide_ft,
            "tide_phase": (env.meta or {}).get("tide_phase"),
            "tide_rate_ft_per_hr": (env.meta or {}).get("tide_rate_ft_per_hr"),
            "route_heading_deg": (env.meta or {}).get("route_heading_deg"),
            "tide_flow_dir_est_deg": _tide_flow_dir_est(
                (env.meta or {}).get("route_heading_deg"),
                (env.meta or {}).get("tide_phase"),
            ),
            "wind_vs_tide_flow_delta_deg": (
                _angle_diff_deg(
                    float(wind_dir),
                    float(_tide_flow_dir_est((env.meta or {}).get("route_heading_deg"), (env.meta or {}).get("tide_phase"))),
                )
                if wind_dir is not None and _tide_flow_dir_est((env.meta or {}).get("route_heading_deg"), (env.meta or {}).get("tide_phase")) is not None
                else None
            ),

        }
    )
    detail = {k: v for k, v in detail.items() if v is not None}

    # Filter non-serializable internal keys from providers meta
    providers_meta = {k: v for k, v in meta.items() if not k.startswith("_")}

    return RideScore(
        t_local=env.t_local,
        lat=env.lat,
        lon=env.lon,
        score_0_100=float(round(score, 1)),
        label=label,
        reasons=reasons,
        detail={
            **detail,
            "wave_source": wave_source,
            "fetch_nm": meta.get("fetch_nm"),
            "providers": providers_meta,
        },
    )
