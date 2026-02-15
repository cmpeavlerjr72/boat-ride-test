from __future__ import annotations

from typing import Any, Dict, List

from boat_ride.core.models import EnvAtPoint, TripPlan

from boat_ride.providers.waves_inland import InlandWaveInputs, compute_inland_waves

try:
    from boat_ride.geo.fetch_calculator import effective_fetch_nm as _effective_fetch
except ImportError:
    _effective_fetch = None



def _compute_fetch_chop(wind_kt: float, fetch_nm: float) -> tuple[float, float]:
    """
    Simple inland chop model (POC):
      height grows with wind and sqrt(fetch); short period.
    Tuned for plausibility, not strict ocean-physics.
    """
    if wind_kt <= 0 or fetch_nm <= 0:
        return 0.0, 0.0

    f = max(0.05, min(float(fetch_nm), 10.0))

    # ~0.4ft at 5kt & 1nm; ~2.3ft at 20kt & 2nm
    h_ft = 0.08 * float(wind_kt) * (f ** 0.5)
    h_ft = max(0.0, min(h_ft, 4.5))

    t_s = 2.5 + 0.6 * (f ** 0.5) + 0.05 * float(wind_kt)
    t_s = max(2.0, min(t_s, 6.5))

    return h_ft, t_s


def _should_suppress_ndbc(base_meta: Dict[str, Any], overlay_meta: Dict[str, Any]) -> bool:
    """
    Inland gate (order-independent):
      - if protected water (small fetch)
      - AND buoy is far
      => do NOT apply buoy wave height at this point
    """
    # IMPORTANT: fetch_nm might come from a later provider (Fetch),
    # and ndbc_distance_nm might come from an earlier provider (NDBC),
    # so check BOTH dicts.
    fetch_nm = overlay_meta.get("fetch_nm")
    if fetch_nm is None:
        fetch_nm = base_meta.get("fetch_nm")

    dist_nm = overlay_meta.get("ndbc_distance_nm")
    if dist_nm is None:
        dist_nm = base_meta.get("ndbc_distance_nm")

    if fetch_nm is None or dist_nm is None:
        return False

    try:
        fetch_nm = float(fetch_nm)
        dist_nm = float(dist_nm)
    except Exception:
        return False

    return fetch_nm <= 2.0 and dist_nm >= 10.0


class ChainProvider:
    def __init__(self, providers: List[Any]):
        self.providers = providers

    def get_env_series(self, plan: TripPlan) -> List[EnvAtPoint]:
        if not self.providers:
            return []

        series = self.providers[0].get_env_series(plan)

        for prov in self.providers[1:]:
            overlay = prov.get_env_series(plan)

            if len(overlay) != len(series):
                raise RuntimeError(
                    f"Provider length mismatch: {prov} overlay={len(overlay)} base={len(series)}"
                )

            merged: List[EnvAtPoint] = []
            for b, o in zip(series, overlay):
                base_meta = dict(b.meta or {})
                overlay_meta = dict(o.meta or {})

                # Determine if this overlay is NDBC
                # Determine if offshore buoy waves should be suppressed (regardless of provider order)
                suppress_ndbc = _should_suppress_ndbc(
                    base_meta=base_meta,
                    overlay_meta={**base_meta, **overlay_meta},
                )

                # Apply overlays, but protect wave fields if suppressing buoy waves
                def choose(field: str, o_val, b_val):
                    if suppress_ndbc and field in ("wave_height_ft", "wave_period_s", "wave_dir_deg"):
                        return b_val
                    return o_val if o_val is not None else b_val

                # Build meta (merged)
                meta: Dict[str, Any] = {}
                meta.update(base_meta)
                meta.update(overlay_meta)

                if suppress_ndbc:
                    b.wave_height_ft = None
                    b.wave_period_s = None
                    b.wave_dir_deg = None
                    meta["ndbc_suppressed"] = True
                    meta["ndbc_suppressed_reason"] = "protected_water_small_fetch_and_far_buoy"

                # If we have wind + fetch and no waves yet, synthesize inland chop
                fetch_nm = meta.get("fetch_nm")
                if b.wave_height_ft is None and fetch_nm is not None and b.wind_speed_kt is not None:
                    try:
                        h_ft, t_s = compute_inland_waves(
                            InlandWaveInputs(
                                wind_kt=float(b.wind_speed_kt),
                                fetch_nm=float(fetch_nm),
                                depth_m=(meta.get("depth_m") if isinstance(meta, dict) else None),
                            )
                        )

                        b.wave_height_ft = h_ft
                        b.wave_period_s = t_s
                        meta["waves_source"] = "fetch"

                        meta["wave_source_note"] = f"fetch_chop({fetch_nm}nm)"
                    except Exception as e:
                        meta["fetch_chop_error"] = f"{type(e).__name__}: {e}"

                merged.append(
                    EnvAtPoint(
                        t_local=b.t_local,
                        lat=b.lat,
                        lon=b.lon,
                        wind_speed_kt=choose("wind_speed_kt", o.wind_speed_kt, b.wind_speed_kt),
                        wind_gust_kt=choose("wind_gust_kt", o.wind_gust_kt, b.wind_gust_kt),
                        wind_dir_deg=choose("wind_dir_deg", o.wind_dir_deg, b.wind_dir_deg),
                        precip_prob=choose("precip_prob", o.precip_prob, b.precip_prob),
                        wave_height_ft=choose("wave_height_ft", o.wave_height_ft, b.wave_height_ft),
                        wave_period_s=choose("wave_period_s", o.wave_period_s, b.wave_period_s),
                        wave_dir_deg=choose("wave_dir_deg", o.wave_dir_deg, b.wave_dir_deg),
                        tide_ft=choose("tide_ft", o.tide_ft, b.tide_ft),
                        current_kt=choose("current_kt", o.current_kt, b.current_kt),
                        current_dir_deg=choose("current_dir_deg", o.current_dir_deg, b.current_dir_deg),
                        meta=meta,
                    )
                )

            series = merged

        # Post-merge: if we have _fetch_result and wind direction, compute
        # effective (SPM-weighted) fetch and update fetch_nm in meta
        if _effective_fetch is not None:
            for env in series:
                fr = (env.meta or {}).get("_fetch_result")
                wd = env.wind_dir_deg
                if fr is not None and wd is not None:
                    eff = _effective_fetch(fr, wd)
                    env.meta["fetch_nm"] = eff
                    env.meta["fetch_effective_method"] = "spm_weighted"

        return series
