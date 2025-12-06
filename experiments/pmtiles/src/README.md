# PMTiles Exporter

Generate optimized PMTiles archives from Supabase location data for MapLibre visualization.

## Quick Start

```bash
cd experiments/pmtiles/src

# All-time data (~700KB output)
uv run python cli.py --secrets ../../../app/secrets.json --output-dir ../output --all-time

# Last 30 days
uv run python cli.py --secrets ../../../app/secrets.json --output-dir ../output --days 30

# Force re-download (skip cache)
uv run python cli.py --secrets ../../../app/secrets.json --output-dir ../output --all-time --force-refetch
```

## Requirements

- `SUPABASE_URL` and `DB_PASSWORD` in secrets file (or via env/flags)
- Tippecanoe installed (`brew install tippecanoe`)

## Output

The PMTiles contains these layers:
- **Per-topic tracks** (e.g., `Living in Buenos Aires`, `Portugal-Japan 2025`) - LineStrings per trip
- **`flights`** - Detected high-speed segments (>200km/h, min 50km, min 10min)

Locations layer excluded by default for size optimization. Add `--include-locations` if needed.

## Size Optimization

| Data | Size |
|------|------|
| Raw DB export | 337 MB |
| Optimized PMTiles | **712 KB** |
| Reduction | 99.8% |

Achieved via:
- Ramer-Douglas-Peucker line simplification (default 300m tolerance)
- Coordinate precision reduction (5 decimals = ~1m)
- Minimal metadata (only timestamps)
- Excluded locations layer
- Tippecanoe `--drop-densest-as-needed`, `--coalesce-densest-as-needed`

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--all-time` | off | Fetch all data instead of last N days |
| `--days` | 7 | Lookback window when not using --all-time |
| `--simplify-km` | 0.1 | Line simplification tolerance (higher = smaller) |
| `--max-zoom` | 10 | Highest tile zoom level (lower = smaller) |
| `--force-refetch` | off | Re-download from DB even if cached |
| `--include-locations` | off | Add raw points layer (increases size ~10x) |
| `--keep-geojson` | off | Keep intermediate GeoJSON files |
| `--gap-hours` | 3 | Split tracks when time gap exceeds this |
| `--flight-gap-hours` | 12 | Max gap for flight detection |
| `--outlier-km` | 50 | Remove isolated slow points beyond this distance |

## Tuning File Size

```bash
# Smaller (~500KB): more aggressive simplification
uv run python cli.py ... --simplify-km 0.5 --max-zoom 8

# Larger but sharper (~2MB): less simplification
uv run python cli.py ... --simplify-km 0.05 --max-zoom 12
```

## Caching

Raw data is cached in `output/geojson/{base}_raw.json`. Subsequent runs skip DB fetch unless `--force-refetch` is used.
