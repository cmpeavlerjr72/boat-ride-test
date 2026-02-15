# Boat Ride - Backend Architecture

## What This Is
A scoring engine for boating conditions along a planned route. Evaluates wind, waves, tides, fetch, and precipitation to produce a 0-100 ride quality score per sample point. The backend serves a React Native mobile app where users draw routes on a map.

## Tech Stack
- **Python 3.10+**, Pydantic v2, NumPy
- **FastAPI** REST API (`src/boat_ride/api.py`)
- **Shapely + pyshp** for dynamic fetch ray-casting against Natural Earth coastline
- **Deployed on Render** (Docker) at the repo's GitHub origin

## Key API Endpoints
- `POST /score-route` — accepts `{route: [{lat, lon}], start_time, end_time, timezone, boat?, provider?}`, returns scored results with per-point scores, labels, and detailed conditions
- `GET /health` — health check

## Project Structure
```
src/boat_ride/
├── api.py                    # FastAPI app (POST /score-route, GET /health)
├── cli.py                    # CLI entry point (python -m boat_ride.cli)
├── core/
│   ├── engine.py             # run_engine(plan, provider) -> list[RideScore]
│   ├── models.py             # TripPlan, BoatProfile, RoutePoint, EnvAtPoint, RideScore
│   ├── route.py              # normalize_route() - resample polyline to uniform points
│   └── scoring.py            # score_point() - 0-100 heuristic scoring
├── contracts/
│   └── route_contract.py     # NormalizedPoint, NormalizedRoute dataclasses
├── geo/
│   ├── shoreline.py          # ShorelineData - downloads/caches Natural Earth coastline
│   └── fetch_calculator.py   # FetchCalculator - 16-ray fetch, effective_fetch_nm (SPM)
└── providers/
    ├── base.py               # EnvProvider ABC
    ├── chain.py              # ChainProvider - merges multiple providers, inland gate
    ├── combined.py           # build_provider("nws+ndbc+fetch+coops")
    ├── fetch.py              # FetchChopProvider - dynamic or manual fetch_nm
    ├── nws.py                # NWSProvider - NOAA weather (wind, precip)
    ├── ndbc.py               # NDBCWaveProvider - buoy wave observations
    ├── coops.py              # COOPSTideProvider - tide predictions
    ├── nwps.py               # NWPSProvider - stub (nearshore waves)
    ├── usace.py              # USACEProvider - stub (river gauges)
    ├── waves_inland.py       # SMB/JONSWAP inland wave growth model
    └── http.py               # HTTPClient utility with retries
```

## How Scoring Works
1. `TripPlan` defines boat, route points, time window, sample interval
2. `run_engine()` normalizes the route, then asks the provider chain for `EnvAtPoint` at each sample time
3. Provider chain runs: NWS (wind) → NDBC (waves) → Fetch (fetch_nm) → CO-OPS (tides)
4. Chain merges results with inland gate logic (suppresses offshore buoy waves in protected water)
5. If wind + fetch but no waves, synthesizes inland chop via SMB model
6. `score_point()` applies penalty heuristics: wind, waves, period, steepness, tide flow, precip

## Dynamic Fetch
- `FetchCalculator` shoots 16 rays from each point against Natural Earth coastline
- Coastline shapefile (~5MB) cached to `~/.boat_ride/data/` (or `BOAT_RIDE_DATA_DIR`)
- `effective_fetch_nm()` computes SPM cos²-weighted average in wind direction
- Auto-classifies waterway: inland (<3nm min fetch), coastal (3-20nm), offshore (>20nm)

## Timezone Handling
- `TripPlan.sample_times` produces timezone-aware datetimes using `zoneinfo.ZoneInfo`
- All providers compare aware datetimes safely (strip tz if mismatched)
- `EnvAtPoint.t_local` stays as a display string; internal math uses aware `datetime`

## Trip JSON Format (what the mobile app will POST)
```json
{
  "route": [{"lat": 30.39, "lon": -88.88}, {"lat": 30.33, "lon": -88.72}],
  "start_time": "2026-01-22 08:00",
  "end_time": "2026-01-22 12:00",
  "timezone": "America/New_York",
  "sample_every_minutes": 20,
  "boat": {"name": "My Boat", "length_ft": 22, "beam_ft": 8.5, "max_safe_wind_kt": 25, "max_safe_wave_ft": 4.0},
  "provider": "nws+ndbc+fetch+coops"
}
```

## Running Locally
```bash
pip install -e .
# CLI
python -m boat_ride.cli --trip trips/sample_trip.json --provider nws+ndbc+fetch+coops --debug
# API
uvicorn boat_ride.api:app --reload
```

## Known Limitations / Future Work
- Providers run sequentially (could be async for speed)
- No server-side response caching yet (each request re-queries NWS/NDBC/CO-OPS)
- NWPS and USACE providers are stubs
- No auth on the API
- Scoring takes 10-20s with full provider stack (mobile needs loading UX)
