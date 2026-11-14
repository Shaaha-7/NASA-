# Curated science sites

Put one GeoJSON file per region here, named `<region_id>.geojson` (for example `jezero.geojson`).
`prepare_data.py` copies it into the processed region, and the map shows each site as a science pin.

**Rule: every site must come from a real, citable source.** Never invent coordinates or observations.
Use the Perseverance waypoints (sol positions) or a published paper/map as the source.

Each feature:

```json
{
  "type": "Feature",
  "geometry": {"type": "Point", "coordinates": [77.4, 18.45]},
  "properties": {
    "id": "site-01",
    "kind": "science_site",
    "name": "Name used in the source",
    "goal_id": "G1",
    "observation": "What was observed, in one sentence",
    "mission": "Mars 2020",
    "instrument": "SuperCam / PIXL / Mastcam-Z / CRISM ...",
    "observation_date": "YYYY-MM-DD or sol N",
    "why_it_matters": "One sentence tying it to the science goal",
    "source": "Short citation",
    "source_url": "https://...",
    "measured_or_derived": "measured"
  }
}
```

Coordinates: [lon, lat], degrees, east-positive longitude, planetocentric latitude.
Copy `jezero.TEMPLATE.geojson` to `jezero.geojson` and replace the example.
