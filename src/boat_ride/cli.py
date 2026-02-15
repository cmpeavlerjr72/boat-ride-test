from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from rich.console import Console
from rich.table import Table

from boat_ride.core.engine import run_engine
from boat_ride.core.models import TripPlan
from boat_ride.providers.combined import build_provider


def _read_trip(path: Path) -> TripPlan:
    data = json.loads(path.read_text(encoding="utf-8"))
    return TripPlan(**data)


def _save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="nws+ndbc+fetch+coops", help="e.g. nws+ndbc+fetch+coops")
    ap.add_argument("--trip", default="trips/sample_trip.json", help="Path to a trip JSON file")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    trip_path = Path(args.trip)
    plan = _read_trip(trip_path)

    provider = build_provider(args.provider)

    scores = run_engine(plan, provider)
    # Ensure deterministic route order for downstream mapping
    scores = sorted(scores, key=lambda s: s.t_local)


    console = Console()

    table = Table(title=f"Boat Ride POC — {plan.trip_id}")
    table.add_column("Time")
    table.add_column("Lat")
    table.add_column("Lon")
    table.add_column("Score")
    table.add_column("Label")
    table.add_column("Wind kt")
    table.add_column("PoP%")
    table.add_column("Wave ft")
    table.add_column("Per s")
    table.add_column("Obs buoy")
    table.add_column("Dist nm")
    table.add_column("Obs time")
    table.add_column("Errs")

    debug_rows: List[dict] = []

    for s in scores:
        d = s.detail or {}
        env_meta = d.get("providers", {}) if isinstance(d.get("providers", {}), dict) else {}

        # compact error summary (if any provider wrote errors into meta)
        errs = []
        for k, v in env_meta.items():
            if isinstance(v, str) and ("error" in v.lower()):
                errs.append(f"{k}:{v}")
        errs_txt = "; ".join(errs)[:120]

        table.add_row(
            s.t_local,
            f"{s.lat:.5f}",
            f"{s.lon:.5f}",
            f"{s.score_0_100:.1f}",
            s.label,
            f"{d.get('wind_kt', '')}",
            f"{int((d.get('pop', 0.0) or 0.0) * 100)}",
            f"{d.get('wave_ft', '')}",
            f"{d.get('wave_period_s', '')}" if "wave_period_s" in d else "",
            str(d.get("buoy_id", "")),
            str(d.get("buoy_dist_nm", "")),
            str(d.get("buoy_obs_time", "")),
            errs_txt,
        )

        if args.debug:
            debug_rows.append(
                {
                    "t_local": s.t_local,
                    "lat": s.lat,
                    "lon": s.lon,
                    "score_0_100": s.score_0_100,
                    "label": s.label,
                    "reasons": s.reasons,
                    "detail": s.detail,
                }
            )

    console.print(table)

    # save last run
    trips_dir = Path("trips")
    _save_json(trips_dir / "last_run_scores.json", [s.model_dump() for s in scores])
    console.print(f"Saved: {(trips_dir / 'last_run_scores.json').resolve()}")

    if args.debug:
        _save_json(trips_dir / "last_run_debug.json", debug_rows)
        console.print(f"Saved: {(trips_dir / 'last_run_debug.json').resolve()}")


if __name__ == "__main__":
    main()
