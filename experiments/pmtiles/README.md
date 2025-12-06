# PMTiles last-week exporter

Fetch the past week of rows from the Supabase `locations` table and turn them into a single PMTiles archive (all zoom levels) for quick visualization.

## Run

```bash
uv run pmtiles-last-week \
  --secrets app/secrets.json \
  --output-dir output
```

Required inputs:
- `SUPABASE_URL` and either `DB_PASSWORD` or `AUTH_PASSWORD` in `app/secrets.json` (or set via env/flags).
- Tippecanoe installed locally (`brew install tippecanoe`).

Flags:
- `--days` (default 7) changes the lookback window.
- `--max-zoom` (default 14) sets the highest zoom for Tippecanoe.
- `--keep-geojson` keeps the intermediate GeoJSON instead of deleting it after tile generation.
- `--gap-hours` (default 3) splits line segments when there’s a big time gap to avoid long jumps.
- `--flight-gap-hours` (default 12) allows flight detection to bridge sparse points within this time window.
- `--outlier-km` (default 50) removes isolated, slow points from track/flight building to avoid stray spikes.

Notes:
- Outputs now live under `output`, with GeoJSON in `output/geojson` and filenames keyed by window, e.g. `locations_last_30d.pmtiles`.
- For the last 3 months: `uv run pmtiles-last-week --days 90 --secrets app/secrets.json --output-dir output --keep-geojson` (keeping GeoJSON is handy for debugging).
- The PMTiles now has multiple layers:
  - `locations`: all points with metadata preserved.
  - `track_tags`: LineStrings ordered by time per `tag`, split by gaps.
  - `track_topics`: LineStrings ordered by time per `topic`, split by gaps.
  - `flights`: detected high-speed segments (heuristic, speed > 200km/h, min 50km, min 10min).
  Style the `track_*` layers as strokes and optionally overlay `locations` as dots. Use `flights` for airborne paths. If flights disappear due to sparse sampling, increase `--flight-gap-hours`.
