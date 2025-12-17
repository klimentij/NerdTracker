# PMTiles Pipeline & Flight Detection Proposal

## Objective
Efficiently visualize years of location history (NerdTracker) with temporal/metadata filtering and separate flight visualization, relying on a completely serverless and free-tier infrastructure.

## Architecture Overview
The proposed pipeline runs nightly via GitHub Actions to transform raw Supabase data into highly optimized vector tiles (PMTiles) hosted on Cloudflare R2 (or GitHub Pages), consumed by a MapLibre GL JS frontend. PMTiles remains the simplest serverless option: one static file, range requests over HTTPS, CDN-cacheable, no running tile server. Alternatives like PostGIS + pg_tileserv or streaming raw GeoJSON either add infra cost or do not scale on free tiers.

`Supabase (Source)` -> `Python (Extraction & Processing)` -> `Tippecanoe (Tile Gen)` -> `Cloudflare R2 (Hosting)` -> `Web App (Visualization via MapLibre + pmtiles protocol)`

---

## 1. Flight Segment Detection
Since we cannot rely on manual tagging for all history, we will implement a heuristic-based detection algorithm in the extraction script.

**Algorithm Logic:**
1.  **Velocity Check**: Calculate speed between consecutive GPS points.
    *   Threshold: Speed > **200 km/h** (approx 108 knots) is a safe baseline for commercial flight (considering takeoff/landing).
2.  **Continuity Check**: A flight candidate must persist for at least **15 minutes**. Data gaps (loss of GPS) followed by a massive location jump > 500km in < 1 hour also imply flight.
3.  **Altitude Validation** (If available): Altitude > 3000m confirms flight.
4.  **Geometry Generation**:
    *   **Ground**: Standard LineString.
    *   **Flight**: Geodesic (Great Circle) LineString to represent the path aesthetically. Visualized as a separate layer (e.g., dashed lines, different color).

**Output**: Two separate GeoJSON feature collections (or layers): `trips` and `flights`.

---

## 2. Vector Tile Generation (Tippecanoe)
We will use [Tippecanoe](https://github.com/mapbox/tippecanoe) to generate a single `.pmtiles` archive. It is the industry standard for large dataset handling.

**Strategy:**
*   **Layers**: Separate `trips` and `flights` layers within the same PMTiles file allow for independent styling and toggling.
*   **Zoom Levels**: `-zg` (Automatically guess max zoom, likely ~12-14) to ensuring detail at street level.
*   **Attributes (Crucial for Filtering)**:
    *   Include minimal metadata in tiles for performance: `timestamp` (Unix Epoch), `tag_id`, `type` (flight/ground).
    *   **Hybrid Approach**: Do *not* store heavy text (descriptions, raw JSON) in tiles. Store a `record_id`. On click, fetch full details from Supabase using `record_id`.
*   **Simplification**: Use `--drop-densest-as-needed` to keep tile sizes small at low zoom levels (viewing the whole world).

**Command Draft** (use `-L` for layers; keep attrs light):
```bash
tippecanoe -o locations.pmtiles \
  -L trips:trips.geojson \
  -L flights:flights.geojson \
  --minimum-zoom=0 --maximum-zoom=14 \
  --drop-densest-as-needed \
  --include=timestamp --include=tag_id --include=record_id
```
*   If `flights` need more fidelity, consider generating them without simplification (`--no-line-simplification`) in a separate layer invocation.
*   Validate that `record_id` is unique and small; avoid heavy text fields in tiles.

---

## 3. Visualization & Filtering (MapLibre GL JS)
Switch the frontend from Leaflet + raw JSON to `maplibre-gl` with the `pmtiles` protocol so the browser streams vector tiles directly.

```javascript
import maplibregl from 'maplibre-gl';
import { PMTiles, Protocol } from 'pmtiles';

const protocol = new Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

const map = new maplibregl.Map({
  container: 'map',
  style: { version: 8, sources: {}, layers: [] },
});

map.on('load', () => {
  map.addSource('tracks', {
    type: 'vector',
    url: 'pmtiles://https://<r2-bucket>/locations.pmtiles',
  });

  map.addLayer({
    id: 'trips',
    type: 'line',
    source: 'tracks',
    'source-layer': 'trips',
    paint: { 'line-color': '#e74c3c', 'line-width': 2 },
  });

  map.addLayer({
    id: 'flights',
    type: 'line',
    source: 'tracks',
    'source-layer': 'flights',
    paint: { 'line-color': '#3498db', 'line-dasharray': [2, 2], 'line-width': 2 },
  });
});
```

**Filtering Years of Data:**
Instead of loading different files, we load one optimized PMTiles source and filter on the client GPU.
```javascript
// Example: Filter for 2023 data only
map.setFilter('trips-layer', [
  'all',
  ['>=', 'timestamp', 1672531200], // Jan 1 2023
  ['<=', 'timestamp', 1704067199]  // Dec 31 2023
]);
```
*   **Efficiency**: PMTiles uses HTTP Range Requests. The browser only fetches the specific kilobytes of data for the tiles currently in the viewport.
*   **CORS on R2**: Allow `GET, HEAD, OPTIONS` with headers `Range, Accept, Origin`; bucket must be public-read so range requests succeed.

---

## 4. Automation (GitHub Action)
A nightly workflow to keep the map up to date.

*   **Schedule**: `cron: '0 2 * * *'` (2 AM UTC).
*   **Workflow Steps**:
    1.  **Checkout**: Repo code.
    2.  **Python Script**:
        *   Connect to Supabase.
        *   Fetch all points (incremental fetch is harder with reprocessing needed for simplification, full fetch is fine for <1M points).
        *   Run Flight Detection.
        *   Write `trips.geojson` and `flights.geojson` to disk.
    3.  **Install Tippecanoe**: `sudo apt-get install tippecanoe` (or build from source).
    4.  **Generate Tiles**: Run the `tippecanoe` command.
    5.  **Upload**: Use `rclone` or action to push `locations.pmtiles` to Cloudflare R2.
        *   *Why R2?* Zero egress fees. AWS S3 charges for data transfer. R2 is perfect for map tiles.

## 5. Free-Tier Considerations
*   **Compute**: GitHub Actions standard runners are free for public repos (and 2000 mins/mo for private). Processing < 5GB of JSON is well within limits.
*   **Storage/Bandwidth**: Cloudflare R2 offers 10GB storage and 10 million requests/month for free. This is sufficient for personal location history (even with nightly updates).
*   **Database**: Supabase Free Tier (500MB) holds millions of GPS text records easily.

## Next Steps
1.  Isolate the Flight Detection logic into `scripts/process_locations.py`.
2.  Create the GitHub Action YAML.
3.  Set up Cloudflare R2 bucket.
4.  Frontend: swap Leaflet to MapLibre GL JS + `pmtiles` protocol; add layers/filters as above.
5.  Validation after upload:
    * `curl -I https://<r2-url>/locations.pmtiles` should return `Accept-Ranges: bytes`.
    * Open the app; watch the browser network tab for range requests, and ensure `trips` / `flights` layers draw at expected zooms.
