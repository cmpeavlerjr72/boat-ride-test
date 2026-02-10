from __future__ import annotations

import math
from datetime import datetime, timedelta

from boat_ride.core.models import TripPlan, EnvAtPoint
from boat_ride.providers.base import EnvProvider


def _parse_local(dt_str: str) -> datetime:
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M")


class MockProvider(EnvProvider):
    """
    Deterministic fake data so the pipeline runs end-to-end without APIs.
    Produces slightly different conditions across time + along the route.
    """

    def get_env_series(self, plan: TripPlan) -> list[EnvAtPoint]:
        start = _parse_local(plan.start_time_local)
        end = _parse_local(plan.end_time_local)
        step = timedelta(minutes=plan.sample_every_minutes)

        out: list[EnvAtPoint] = []
        t = start
        idx = 0

        # Walk points in a loop so we don't need real speed/distance yet
        npts = max(1, len(plan.route))

        while t <= end:
            p = plan.route[idx % npts]

            # Time-driven “weather” signal
            phase = (t - start).total_seconds() / max(1.0, (end - start).total_seconds())
            wiggle = math.sin(phase * math.tau)

            # Route-driven variation
            geo = math.sin((p.lat + p.lon) * 10)

            wind = 10 + 8 * max(0.0, wiggle) + 2 * geo
            gust = wind + 5 + 2 * max(0.0, -wiggle)

            waves = 1.0 + 1.5 * max(0.0, wiggle) + 0.5 * abs(geo)
            period = 6.0 + 2.0 * (1 - phase)

            precip = max(0.0, min(1.0, 0.15 + 0.35 * max(0.0, -wiggle)))

            # Tide/current toy model
            tide = 1.5 * math.sin(phase * math.tau)
            current = 0.5 + 0.6 * abs(math.cos(phase * math.tau))

            out.append(
                EnvAtPoint(
                    t_local=t.strftime("%Y-%m-%d %H:%M"),
                    lat=p.lat,
                    lon=p.lon,
                    wind_speed_kt=float(round(wind, 2)),
                    wind_gust_kt=float(round(gust, 2)),
                    wind_dir_deg=float(round((220 + 40 * wiggle) % 360, 1)),
                    wave_height_ft=float(round(waves, 2)),
                    wave_period_s=float(round(period, 2)),
                    wave_dir_deg=float(round((200 + 30 * geo) % 360, 1)),
                    precip_prob=float(round(precip, 3)),
                    tide_ft=float(round(tide, 2)),
                    current_kt=float(round(current, 2)),
                    current_dir_deg=float(round((90 + 60 * geo) % 360, 1)),
                )
            )

            t += step
            idx += 1

        return out
