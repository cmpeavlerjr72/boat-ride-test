from __future__ import annotations

import json
from pathlib import Path


LABEL_COLOR = {
    "great": "#2ecc71",
    "ok": "#f1c40f",
    "rough": "#e67e22",
    "avoid": "#e74c3c",
}


def main() -> None:
    trips_dir = Path("trips")
    scores_path = trips_dir / "last_run_scores.json"
    out_path = trips_dir / "last_run_map.html"

    scores = json.loads(scores_path.read_text(encoding="utf-8"))
    if not scores:
        raise SystemExit("No scores found in trips/last_run_scores.json")

    # Build per-segment colored polylines using start label
    segs = []
    for i in range(len(scores) - 1):
        a = scores[i]
        b = scores[i + 1]
        label = a.get("label", "ok")
        segs.append(
            {
                "a": [a["lat"], a["lon"]],
                "b": [b["lat"], b["lon"]],
                "color": LABEL_COLOR.get(label, "#3498db"),
                "label": label,
                "score": a.get("score_0_100"),
                "t": a.get("t_local"),
                "detail": a.get("detail", {}),
            }
        )


    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Boat Ride – Last Run Map</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    body {{ margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
    #map {{ height: 100vh; width: 100vw; }}
    .popup pre {{ white-space: pre-wrap; font-size: 12px; }}
  </style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const scores = {json.dumps(scores)};
  const segs = {json.dumps(segs)};

  const map = L.map('map');

  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors'
  }}).addTo(map);

  function fmt(obj) {{
    try {{ return JSON.stringify(obj, null, 2); }} catch(e) {{ return String(obj); }}
  }}

  // markers
  scores.forEach((s, idx) => {{
    const title = (s.detail && s.detail.providers && s.detail.providers.route_name) ? s.detail.providers.route_name : s.t_local;
    const popup = `
      <div class="popup">
        <b>${{title}}</b><br/>
        <b>Time:</b> ${{s.t_local}}<br/>
        <b>Score:</b> ${{s.score_0_100}} (${{s.label}})<br/>
        <b>Lat/Lon:</b> ${{s.lat.toFixed(5)}}, ${{s.lon.toFixed(5)}}<br/>
        <b>Detail:</b>
        <pre>${{fmt(s.detail || {{}})}}</pre>
      </div>
    `;
    L.circleMarker([s.lat, s.lon], {{ radius: 5 }}).addTo(map).bindPopup(popup);
  }});

  // colored segments
  segs.forEach((seg) => {{
    const popup = `
      <div class="popup">
        <b>${{seg.t}}</b><br/>
        <b>Segment label:</b> ${{seg.label}}<br/>
        <b>Score:</b> ${{seg.score}}<br/>
        <b>Detail:</b>
        <pre>${{fmt(seg.detail || {{}})}}</pre>
      </div>
    `;
    L.polyline([seg.a, seg.b], {{ color: seg.color, weight: 6, opacity: 0.9 }}).addTo(map).bindPopup(popup);
  }});

  // fit bounds
  const bounds = L.latLngBounds(scores.map(s => [s.lat, s.lon]));
  map.fitBounds(bounds.pad(0.2));
</script>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote: {out_path.resolve()}")


if __name__ == "__main__":
    main()
