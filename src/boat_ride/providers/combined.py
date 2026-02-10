from __future__ import annotations

from boat_ride.core.models import TripPlan, EnvAtPoint
from boat_ride.providers.base import EnvProvider


class CombinedProvider(EnvProvider):
    """
    Runs two providers and merges non-null fields from overlay into base.

    Intended use:
      base = NWSProvider()  -> wind/precip
      overlay = NDBCWaveProvider() -> waves
    """

    def __init__(self, base: EnvProvider, overlay: EnvProvider):
        self.base = base
        self.overlay = overlay

    def get_env_series(self, plan: TripPlan) -> list[EnvAtPoint]:
        try:
            base_series = self.base.get_env_series(plan)
        except Exception as e:
            base_series = None
            base_err = e

        try:
            overlay_series = self.overlay.get_env_series(plan)
        except Exception as e:
            overlay_series = None
            overlay_err = e

        if base_series is None and overlay_series is None:
            raise RuntimeError(f"Both providers failed: base={base_err} overlay={overlay_err}")

        if base_series is None:
            base_series = [
                EnvAtPoint(
                    t_local=o.t_local,
                    lat=o.lat,
                    lon=o.lon,
                    wind_speed_kt=0.0,
                    wind_gust_kt=None,
                    wind_dir_deg=None,
                    wave_height_ft=None,
                    wave_period_s=None,
                    wave_dir_deg=None,
                    precip_prob=None,
                    tide_ft=None,
                    current_kt=None,
                    current_dir_deg=None,
                    meta={"combined_note": f"base provider failed: {type(base_err).__name__}"},
                )
                for o in overlay_series
            ]

        if overlay_series is None:
            return base_series

        if len(base_series) != len(overlay_series):
            raise RuntimeError(f"Provider series length mismatch: {len(base_series)} vs {len(overlay_series)}")

        merged: list[EnvAtPoint] = []
        for b, o in zip(base_series, overlay_series):
            meta = {}
            meta.update(b.meta or {})
            meta.update(o.meta or {})

            merged.append(
                EnvAtPoint(
                    t_local=b.t_local,
                    lat=b.lat,
                    lon=b.lon,
                    wind_speed_kt=b.wind_speed_kt,
                    wind_gust_kt=b.wind_gust_kt,
                    wind_dir_deg=b.wind_dir_deg,
                    wave_height_ft=o.wave_height_ft if o.wave_height_ft is not None else b.wave_height_ft,
                    wave_period_s=o.wave_period_s if o.wave_period_s is not None else b.wave_period_s,
                    wave_dir_deg=o.wave_dir_deg if o.wave_dir_deg is not None else b.wave_dir_deg,
                    precip_prob=b.precip_prob,
                    tide_ft=b.tide_ft,
                    current_kt=b.current_kt,
                    current_dir_deg=b.current_dir_deg,
                    meta=meta,
                )
            )

        return merged


def build_provider(provider_str: str):
    """
    Build a provider stack from CLI string like:
      "nws+ndbc"
      "nws+ndbc+fetch"
      "nws+nwps+coops+ndbc"

    Returns a ChainProvider (preferred) so we can overlay multiple layers.
    """
    tokens = [t.strip().lower() for t in provider_str.split("+") if t.strip()]
    if not tokens:
        tokens = ["nws", "ndbc"]

    # Local imports to avoid circular imports
    from boat_ride.providers.chain import ChainProvider
    from boat_ride.providers.nws import NWSProvider
    from boat_ride.providers.ndbc import NDBCWaveProvider
    from boat_ride.providers.fetch import FetchChopProvider
    from boat_ride.providers.nwps import NWPSProvider
    from boat_ride.providers.coops import COOPSTideProvider
    from boat_ride.providers.usace import USACEProvider

    providers = []
    for t in tokens:
        if t == "nws":
            providers.append(NWSProvider())
        elif t == "ndbc":
            providers.append(NDBCWaveProvider())
        elif t == "fetch":
            providers.append(FetchChopProvider())
        elif t == "nwps":
            providers.append(NWPSProvider())
        elif t in ("coops", "tide"):
            providers.append(COOPSTideProvider())
        elif t == "usace":
            providers.append(USACEProvider())
        else:
            raise ValueError(f"Unknown provider token: '{t}' (supported: nws, ndbc, fetch, nwps, coops, usace)")

    return ChainProvider(providers)
