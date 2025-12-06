from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import psycopg
from psycopg.rows import dict_row

DEFAULT_POOLER_HOST = "aws-0-us-west-1.pooler.supabase.com"
DEFAULT_DB_NAME = "postgres"
FLIGHT_SPEED_THRESHOLD_KMH = 200.0
FLIGHT_MIN_DISTANCE_KM = 50.0
FLIGHT_MIN_DURATION_MIN = 10.0
FLIGHT_MAX_GAP_HOURS = 12.0
DEFAULT_OUTLIER_KM = 50.0


def parse_project_ref(url: str) -> str:
    if not url:
        raise ValueError("Supabase URL is required to derive project ref")

    without_scheme = url.replace("https://", "").replace("http://", "")
    ref = without_scheme.split(".supabase.co")[0]
    if not ref or ref == without_scheme:
        raise ValueError(f"Could not parse project ref from {url}")
    return ref


def load_config(args: argparse.Namespace) -> Tuple[str, str, str]:
    secrets_path = Path(args.secrets) if args.secrets else None
    secrets: Dict[str, str] = {}
    if secrets_path and secrets_path.exists():
        secrets = json.loads(secrets_path.read_text())

    supabase_url = (
        args.supabase_url
        or os.getenv("SUPABASE_URL")
        or secrets.get("SUPABASE_URL")
    )
    db_password = (
        args.db_password
        or os.getenv("DB_PASSWORD")
        or os.getenv("SUPABASE_DB_PASSWORD")
        or secrets.get("DB_PASSWORD")
        or secrets.get("AUTH_PASSWORD")
    )
    pooler_host = (
        args.pooler_host
        or os.getenv("SUPABASE_POOLER_HOST")
        or DEFAULT_POOLER_HOST
    )

    if not supabase_url:
        raise SystemExit("Missing Supabase URL (set via --supabase-url or SUPABASE_URL).")
    if not db_password:
        raise SystemExit(
            "Missing database password (set via --db-password, DB_PASSWORD, or add DB_PASSWORD/AUTH_PASSWORD to secrets)."
        )

    return supabase_url, db_password, pooler_host


def build_dsn(project_ref: str, password: str, pooler_host: str, port: int) -> str:
    user = f"postgres.{project_ref}"
    return (
        f"host={pooler_host} "
        f"port={port} "
        f"dbname={DEFAULT_DB_NAME} "
        f"user={user} "
        f"password={password} "
        "sslmode=require "
        "options='-c statement_timeout=120000'"
    )


def fetch_locations(
    dsn: str, since_epoch: int
) -> List[Dict[str, object]]:
    query = """
        select
            id,
            lat,
            lon,
            acc,
            alt,
            vel,
            vac,
            p,
            cog,
            rad,
            tag,
            tid,
            topic,
            _type,
            conn,
            batt,
            bs,
            w,
            o,
            m,
            ssid,
            bssid,
            inregions,
            inrids,
            "desc",
            uuid,
            major,
            minor,
            event,
            wtst,
            poi,
            r,
            u,
            t,
            c,
            b,
            steps,
            from_epoch,
            to_epoch,
            request,
            tst,
            created_at
            -- insert_time is server default; select all columns to retain metadata
            , insert_time
        from public.locations
        where tst >= %(cutoff)s
          and lat is not null
          and lon is not null
        order by tst asc
    """
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if since_epoch > 0:
                cur.execute(query, {"cutoff": since_epoch})
            else:
                # Remove the tst clause or pass 0
                query_all = query.replace("where tst >= %(cutoff)s", "where 1=1")
                cur.execute(query_all, {"cutoff": 0})
            rows = cur.fetchall()
            return rows


def features_from_rows(rows: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    features: List[Dict[str, object]] = []
    for row in rows:
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue

        def _int_or_none(value: object) -> int | None:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        props = {
            "id": _int_or_none(row.get("id")),
            "tst": _int_or_none(row.get("tst")),
            "created_at": _int_or_none(row.get("created_at")),
            "tag": row.get("tag"),
            "tid": row.get("tid"),
            "topic": row.get("topic"),
            "_type": row.get("_type"),
            "conn": row.get("conn"),
            "vel": row.get("vel"),
            "acc": row.get("acc"),
            "alt": row.get("alt"),
            "vac": row.get("vac"),
            "p": row.get("p"),
            "cog": row.get("cog"),
            "rad": row.get("rad"),
            "batt": row.get("batt"),
            "bs": row.get("bs"),
            "w": row.get("w"),
            "o": row.get("o"),
            "m": row.get("m"),
            "ssid": row.get("ssid"),
            "bssid": row.get("bssid"),
            "inregions": row.get("inregions"),
            "inrids": row.get("inrids"),
            "desc": row.get("desc"),
            "uuid": row.get("uuid"),
            "major": row.get("major"),
            "minor": row.get("minor"),
            "event": row.get("event"),
            "wtst": _int_or_none(row.get("wtst")),
            "poi": row.get("poi"),
            "r": row.get("r"),
            "u": row.get("u"),
            "t": row.get("t"),
            "c": row.get("c"),
            "b": row.get("b"),
            "steps": row.get("steps"),
            "from_epoch": _int_or_none(row.get("from_epoch")),
            "to_epoch": _int_or_none(row.get("to_epoch")),
            "request": row.get("request"),
            "insert_time": row.get("insert_time").isoformat() if row.get("insert_time") else None,
        }

        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": props,
        }
        features.append(feature)

    return features


def build_track_segments(
    point_features: Sequence[Dict[str, object]],
    max_gap_hours: float,
    forbidden_intervals: List[Tuple[int, int]] | None = None,
) -> List[Dict[str, object]]:
    # Build line segments ordered by timestamp.
    # Split if gap > max_gap_hours OR gap overlaps a forbidden interval (flight).
    if not point_features:
        return []

    # Sort just in case
    # Assuming point_features are already sorted or we sort here (safer)
    pts = sorted(point_features, key=lambda f: f["properties"].get("tst") or 0)
    
    segments: List[List[Dict[str, object]]] = []
    current: List[Dict[str, object]] = []

    # Optimize forbidden checks
    sorted_forbidden = sorted(forbidden_intervals) if forbidden_intervals else []
    
    def is_forbidden(t1: int, t2: int) -> bool:
        # Check if [t1, t2] overlaps significantly with any forbidden interval
        # Actually, if there is a flight [fs, fe], and t1 < fs and t2 > fe, then we bridged it.
        # We want to split if we bridge a flight.
        # So if any flight is contained within (t1, t2), we split.
        if not sorted_forbidden:
            return False
            
        # Binary search or simple iteration (flights are few)
        # We want to find a flight where flight_end > t1 and flight_start < t2
        # But specifically, we are concerned about bridging: t1 <= flight_start AND t2 >= flight_end
        # The gap completely contains the flight.
        
        for fs, fe in sorted_forbidden:
            if fs >= t1 and fe <= t2:
                # Only if the overlap is real (flight duration > 0)
                if fe > fs:
                    return True
            if fs > t2:
                break
        return False

    for feat in pts:
        ts = feat["properties"].get("tst")
        if ts is None:
            continue

        if not current:
            current.append(feat)
            continue

        prev_ts = current[-1]["properties"].get("tst")
        if prev_ts is None:
            current.append(feat)
            continue

        gap_hours = (ts - prev_ts) / 3600.0
        
        should_split = False
        if gap_hours > max_gap_hours:
            should_split = True
        elif is_forbidden(prev_ts, ts):
            should_split = True

        if should_split:
            segments.append(current)
            current = [feat]
        else:
            current.append(feat)

    if current:
        segments.append(current)

    line_features: List[Dict[str, object]] = []
    for seg in segments:
        if len(seg) < 2:
            continue

        coords = [pt["geometry"]["coordinates"] for pt in seg]
        start_ts = seg[0]["properties"].get("tst")
        end_ts = seg[-1]["properties"].get("tst")

        line_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "count": len(seg),
                    # Inherit tag from first point?
                    "tag": seg[0]["properties"].get("tag"),
                },
            }
        )

    return line_features


def build_grouped_tracks(
    point_features: Sequence[Dict[str, object]],
    group_key: str,
    max_gap_hours: float,
) -> List[Dict[str, object]]:
    # Group by tag/topic and build segments per group.
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for feat in point_features:
        key_val = feat["properties"].get(group_key) or "unknown"
        grouped.setdefault(key_val, []).append(feat)

    lines: List[Dict[str, object]] = []
    for key_val, feats in grouped.items():
        feats_sorted = sorted(feats, key=lambda f: f["properties"].get("tst") or 0)
        segs = build_track_segments(feats_sorted, max_gap_hours)
        for seg in segs:
            seg["properties"][group_key] = key_val
        lines.extend(segs)
    return lines


def filter_isolated_points(
    point_features: Sequence[Dict[str, object]],
    drop_km: float,
    max_keep_speed_kmh: float,
) -> List[Dict[str, object]]:
    """Remove outlier points that are far from both neighbors and slow (likely GPS spikes)."""
    if drop_km <= 0:
        return list(point_features)

    pts = sorted(point_features, key=lambda f: f["properties"].get("tst") or 0)
    if len(pts) < 3:
        return pts

    def dist(a: Dict[str, object], b: Dict[str, object]) -> float:
        ca, cb = a["geometry"]["coordinates"], b["geometry"]["coordinates"]
        return haversine_km(ca[1], ca[0], cb[1], cb[0])

    kept: List[Dict[str, object]] = [pts[0]]
    for i in range(1, len(pts) - 1):
        prev_pt, pt, next_pt = pts[i - 1], pts[i], pts[i + 1]
        prev_dist = dist(prev_pt, pt)
        next_dist = dist(pt, next_pt)

        def speed(a: Dict[str, object], b: Dict[str, object]) -> float:
            t1, t2 = a["properties"].get("tst"), b["properties"].get("tst")
            if t1 is None or t2 is None:
                return 0.0
            dt_hr = (t2 - t1) / 3600.0
            if dt_hr <= 0:
                return 0.0
            return dist(a, b) / dt_hr

        prev_speed = speed(prev_pt, pt)
        next_speed = speed(pt, next_pt)

        if prev_dist > drop_km and next_dist > drop_km and max(prev_speed, next_speed) < max_keep_speed_kmh:
            # Drop this isolated, slow point from line building.
            continue

        kept.append(pt)

    kept.append(pts[-1])
    return kept


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import radians, sin, cos, atan2, sqrt

    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def detect_flights(
    point_features: Sequence[Dict[str, object]],
    speed_threshold_kmh: float,
    min_distance_km: float,
    min_duration_min: float,
    max_gap_hours: float,
) -> List[Dict[str, object]]:
    # Simple heuristic: consecutive points with speed above threshold form a flight segment.
    pts = sorted(point_features, key=lambda f: f["properties"].get("tst") or 0)
    flights: List[List[Dict[str, object]]] = []
    current: List[Dict[str, object]] = []

    for i in range(1, len(pts)):
        p1 = pts[i - 1]
        p2 = pts[i]
        t1 = p1["properties"].get("tst")
        t2 = p2["properties"].get("tst")
        if t1 is None or t2 is None:
            continue
        dt_hours = (t2 - t1) / 3600.0
        if dt_hours <= 0:
            continue
        lat1, lon1 = p1["geometry"]["coordinates"][1], p1["geometry"]["coordinates"][0]
        lat2, lon2 = p2["geometry"]["coordinates"][1], p2["geometry"]["coordinates"][0]
        dist_km = haversine_km(lat1, lon1, lat2, lon2)
        speed = dist_km / dt_hours

        is_flight = speed > speed_threshold_kmh or (
            dist_km >= min_distance_km and dt_hours <= max_gap_hours
        )

        if is_flight:
            if not current:
                current.append(p1)
            current.append(p2)
            current.append(p2)
            # Mark points as flight for later exclusion
            p1["_is_flight"] = True
            p2["_is_flight"] = True
        else:
            if current:
                flights.append(current)
                current = []

    if current:
        flights.append(current)

    flight_features: List[Dict[str, object]] = []
    for seg in flights:
        if len(seg) < 2:
            continue
        # compute length and duration
        total_dist = 0.0
        for i in range(1, len(seg)):
            a = seg[i - 1]["geometry"]["coordinates"]
            b = seg[i]["geometry"]["coordinates"]
            total_dist += haversine_km(a[1], a[0], b[1], b[0])

        start_ts = seg[0]["properties"].get("tst")
        end_ts = seg[-1]["properties"].get("tst")
        if start_ts is None or end_ts is None:
            continue
        duration_min = (end_ts - start_ts) / 60.0

        if total_dist < min_distance_km or duration_min < min_duration_min:
            continue

        flight_features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [pt["geometry"]["coordinates"] for pt in seg],
                },
                "properties": {
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "dist_km": round(total_dist, 2),
                    "duration_min": round(duration_min, 1),
                    "tag": seg[0]["properties"].get("tag"),
                    "topic": seg[0]["properties"].get("topic"),
                    "count": len(seg),
                },
            }
        )

    return flight_features

    # Removed flight_point_obj_ids return since we mark in-place now



def write_geojson(path: Path, features: List[Dict[str, object]]) -> None:
    payload = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(payload))


def ensure_tippecanoe(bin_name: str) -> str:
    resolved = shutil.which(bin_name)
    if not resolved:
        raise SystemExit(
            f"tippecanoe binary '{bin_name}' not found. Install tippecanoe (e.g., brew install tippecanoe)."
        )
    return resolved


def build_pmtiles(
    tippecanoe_bin: str,
    layers: Sequence[Tuple[str, Path]],
    pmtiles_path: Path,
    max_zoom: int,
) -> None:
    args = [
        tippecanoe_bin,
        "-o",
        str(pmtiles_path),
        "--force",
        "--minimum-zoom=0",
        f"--maximum-zoom={max_zoom}",
        "--drop-densest-as-needed",
    ]

    # Include all metadata fields we attach to points/lines.
    includes = [
        "id",
        "tst",
        "tag",
        "topic",
        "vel",
        "alt",
        "start_ts",
        "end_ts",
        "count",
        "dist_km",
        "duration_min",
    ]
    for inc in includes:
        args.append(f"--include={inc}")

    for layer_name, path in layers:
        args.extend(["-L", f"{layer_name}:{path}"])

    subprocess.run(args, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch last week of locations and generate a PMTiles archive."
    )
    parser.add_argument(
        "--secrets",
        type=str,
        default="app/secrets.json",
        help="Path to secrets JSON containing SUPABASE_URL and DB_PASSWORD/AUTH_PASSWORD.",
    )
    parser.add_argument(
        "--supabase-url",
        type=str,
        help="Supabase project URL (overrides secrets/env).",
    )
    parser.add_argument(
        "--db-password",
        type=str,
        help="Database password (overrides secrets/env).",
    )
    parser.add_argument(
        "--pooler-host",
        type=str,
        help="Supabase pooler host override.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5432,
        help="Database port (default 5432).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Lookback window in days (default: 7).",
    )
    parser.add_argument(
        "--max-zoom",
        type=int,
        default=14,
        help="Highest zoom level for tippecanoe (default: 14).",
    )
    parser.add_argument(
        "--tippecanoe-bin",
        type=str,
        default="tippecanoe",
        help="Tippecanoe binary name/path (default: tippecanoe).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory to write outputs (defaults to ./output).",
    )
    parser.add_argument(
        "--gap-hours",
        type=float,
        default=3.0,
        help="Split lines when the time gap between points exceeds this many hours (default: 3).",
    )
    parser.add_argument(
        "--all-time",
        action="store_true",
        help="Fetch all locations regardless of time.",
    )
    parser.add_argument(
        "--flight-gap-hours",
        type=float,
        default=FLIGHT_MAX_GAP_HOURS,
        help="Treat jumps within this many hours as flights even if points are sparse (default: 12).",
    )
    parser.add_argument(
        "--outlier-km",
        type=float,
        default=DEFAULT_OUTLIER_KM,
        help="Skip points from tracks if they are farther than this from both neighbors and slow (default: 50km).",
    )
    parser.add_argument(
        "--keep-geojson",
        action="store_true",
        help="Keep the intermediate GeoJSON instead of deleting it.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    supabase_url, db_password, pooler_host = load_config(args)
    project_ref = parse_project_ref(supabase_url)
    
    if args.all_time:
        cutoff = 0
    else:
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp())

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    geojson_dir = output_dir / "geojson"
    geojson_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"locations_last_{args.days}d"
    points_geojson_path = geojson_dir / f"{base_name}_points.geojson"
    lines_geojson_path = geojson_dir / f"{base_name}_track.geojson"
    track_tags_geojson_path = geojson_dir / f"{base_name}_track_tags.geojson"
    track_topics_geojson_path = geojson_dir / f"{base_name}_track_topics.geojson"
    flights_geojson_path = geojson_dir / f"{base_name}_flights.geojson"
    pmtiles_path = output_dir / f"{base_name}.pmtiles"

    dsn = build_dsn(project_ref, db_password, pooler_host, args.port)

    print(f"Connecting to {pooler_host} as project {project_ref}...")
    print(f"Running query for the last {args.days} days (may take up to the statement timeout)...")
    rows = fetch_locations(dsn, cutoff)
    if not rows:
        raise SystemExit("No rows returned for the requested window.")

    print(f"Fetched {len(rows)} rows. Building GeoJSON...")
    features = features_from_rows(rows)
    write_geojson(points_geojson_path, features)
    print(f"Wrote point GeoJSON to {points_geojson_path}")

    filtered_for_lines = filter_isolated_points(
        features,
        drop_km=args.outlier_km,
        max_keep_speed_kmh=FLIGHT_SPEED_THRESHOLD_KMH * 0.5,
    )

    flight_features = detect_flights(
        filtered_for_lines,
        speed_threshold_kmh=FLIGHT_SPEED_THRESHOLD_KMH,
        min_distance_km=FLIGHT_MIN_DISTANCE_KM,
        min_duration_min=FLIGHT_MIN_DURATION_MIN,
        max_gap_hours=args.flight_gap_hours,
    )
    write_geojson(flights_geojson_path, flight_features)
    print(f"Wrote flights GeoJSON to {flights_geojson_path} ({len(flight_features)} segments)")

    # Build flight intervals for splitting
    flight_intervals = []
    for f in flight_features:
        s = f["properties"].get("start_ts")
        e = f["properties"].get("end_ts")
        if s and e:
            flight_intervals.append((s, e))

    filtered_for_tracks = [
        pt for pt in filtered_for_lines if not pt.get("_is_flight")
    ]

    # Group by TOPIC (Trip name)
    from collections import defaultdict
    points_by_group = defaultdict(list)
    for pt in filtered_for_tracks:
        # Use topic as the primary grouper, fallback to tag, then 'unknown'
        t = pt["properties"].get("topic") or pt["properties"].get("tag") or "unknown"
        points_by_group[t].append(pt)

    track_layers = []
    
    print(f"Building tracks for {len(points_by_group)} topics...")
    
    # Process each group
    for group_name, pts in points_by_group.items():
        # Sanitize name for filename
        safe_name = "".join(x for x in group_name if x.isalnum() or x in "._- ")
        if not safe_name: 
            safe_name = "track" 
            
        # Lines logic
        lines = build_track_segments(
            pts, 
            max_gap_hours=24*30, 
            forbidden_intervals=flight_intervals
        )
        
        if not lines:
            continue
            
        layer_name = group_name 
        path = geojson_dir / f"track_{safe_name}.geojson"
        write_geojson(path, lines)
        track_layers.append((layer_name, path))

    tippecanoe_bin = ensure_tippecanoe(args.tippecanoe_bin)
    print("Running tippecanoe to generate PMTiles...")
    
    layers = [
        ("locations", points_geojson_path),
        ("flights", flights_geojson_path),
    ]
    # Add track layers
    layers.extend(track_layers)
    
    build_pmtiles(
        tippecanoe_bin,
        layers=layers,
        pmtiles_path=pmtiles_path,
        max_zoom=args.max_zoom,
    )
    print(f"PMTiles written to {pmtiles_path}")

    if not args.keep_geojson:
        if points_geojson_path.exists():
            points_geojson_path.unlink()
        if flights_geojson_path.exists():
            flights_geojson_path.unlink()
        for _, path in track_layers:
            if path.exists():
                path.unlink()
        if flights_geojson_path.exists():
            flights_geojson_path.unlink()
        print("Cleaned up intermediate GeoJSON.")


if __name__ == "__main__":
    main()
