#!/usr/bin/env python3
"""
Supabase -> Dawarich: copy `public.locations` into Dawarich `public.points`.

What it does
- Reads rows from Supabase `public.locations` (FIRST/oldest by `tst ASC`)
- Inserts into Dawarich `public.points`
- Preserves *all* source columns in `raw_data` (jsonb)
- Preserves non-mapped extra metadata in `geodata` (jsonb)
- Sets `points.user_id` (e.g. `--user-id 1`)
- Skips duplicates via: UNIQUE (lonlat, timestamp, user_id)

Typical usage (in your Dawarich VM)
- First 1000 (oldest), user_id=1:
  uv run python scripts/supabase2dawarich.py --limit 1000 --user-id 1

- Dry-run (no insert):
  uv run python scripts/supabase2dawarich.py --limit 10 --user-id 1 --dry-run

Required
- `app/secrets.json` must contain `SUPABASE_URL` and one of: `DB_PASSWORD` / `AUTH_PASSWORD` / `SUPABASE_DB_PASSWORD`
- Local Dawarich DB reachable (defaults: localhost:5432, db=dawarich_development, user=postgres, password=password)

Notes on speed
- Inserts use psycopg3 pipeline + batch commits to avoid long locks and reduce latency.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Optional progress bar
try:
    from tqdm import tqdm  # type: ignore
except Exception:  # pragma: no cover
    tqdm = None

# Try to import psycopg
try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:
    print("Error: psycopg is required. Please install it:")
    print("  pip install psycopg[binary]")
    sys.exit(1)


# --- Supabase connection bits ---
DEFAULT_POOLER_HOST = "aws-0-us-west-1.pooler.supabase.com"
DEFAULT_DB_NAME = "postgres"
DEFAULT_SECRETS_FILE = "app/secrets.json"


def load_supabase_config(secrets_path: str):
    path = Path(secrets_path)
    if not path.exists():
        print(f"Error: Secrets file not found at {path}")
        print("Please ensure you are running from the project root (or pass --secrets).")
        sys.exit(1)

    try:
        secrets = json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in {path}")
        sys.exit(1)

    supabase_url = secrets.get("SUPABASE_URL")
    db_password = (
        secrets.get("DB_PASSWORD")
        or secrets.get("AUTH_PASSWORD")
        or secrets.get("SUPABASE_DB_PASSWORD")
    )

    if not supabase_url:
        print("Error: SUPABASE_URL not found in secrets file.")
        sys.exit(1)
    if not db_password:
        print("Error: DB_PASSWORD (or AUTH_PASSWORD / SUPABASE_DB_PASSWORD) not found in secrets file.")
        sys.exit(1)

    return supabase_url, db_password


def parse_project_ref(url: str) -> str:
    without_scheme = url.replace("https://", "").replace("http://", "")
    return without_scheme.split(".supabase.co")[0]


def build_supabase_dsn(project_ref: str, password: str, pooler_host: str, port: int = 5432) -> str:
    user = f"postgres.{project_ref}"
    return (
        f"host={pooler_host} "
        f"port={port} "
        f"dbname={DEFAULT_DB_NAME} "
        f"user={user} "
        f"password={password} "
        "sslmode=require "
        "options='-c statement_timeout=600000'"
    )


# --- Target (local Dawarich) connection bits ---
def build_dawarich_dsn(host: str, port: int, dbname: str, user: str, password: str) -> str:
    # Local DB typically doesn't need SSL; keep it explicit.
    return (
        f"host={host} "
        f"port={port} "
        f"dbname={dbname} "
        f"user={user} "
        f"password={password} "
        "sslmode=disable"
    )


def _jsonable(v):
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _to_naive_utc_timestamp(val, fallback: datetime) -> datetime:
    """
    Coerce various timestamp representations into a naive UTC datetime suitable
    for Postgres `timestamp without time zone`.
    Supports:
      - datetime
      - int/float epoch seconds or milliseconds
      - ISO-ish strings (best-effort)
    """
    if isinstance(val, datetime):
        return val.replace(tzinfo=None)
    if isinstance(val, (int, float)):
        # Heuristic: ms epochs are usually > 1e12, seconds around 1e9.
        seconds = val / 1000.0 if val > 1_000_000_000_000 else float(val)
        return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(val, str):
        try:
            return (
                datetime.fromisoformat(val.replace("Z", "+00:00"))
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )
        except Exception:
            return fallback
    if val is None:
        return fallback
    return fallback


def _safe_float(v):
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v):
    try:
        if v is None:
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def fetch_first_locations(conn, limit: int):
    q = """
        SELECT *
        FROM public.locations
        WHERE lat IS NOT NULL AND lon IS NOT NULL
        ORDER BY tst ASC
        LIMIT %(limit)s
    """
    with conn.cursor() as cur:
        cur.execute(q, {"limit": limit})
        return cur.fetchall()


def fetch_last_locations(conn, limit: int):
    q = """
        SELECT *
        FROM public.locations
        WHERE lat IS NOT NULL AND lon IS NOT NULL
        ORDER BY tst DESC
        LIMIT %(limit)s
    """
    with conn.cursor() as cur:
        cur.execute(q, {"limit": limit})
        return cur.fetchall()


def _env_first(*names: str, default: str | None = None) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v is not None and str(v).strip() != "":
            return v
    return default


def _has_column(conn, *, schema: str, table: str, column: str) -> bool:
    q = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = %(schema)s
              AND table_name = %(table)s
              AND column_name = %(column)s
        )
    """
    with conn.cursor() as cur:
        cur.execute(q, {"schema": schema, "table": table, "column": column})
        row = cur.fetchone()
        # row_factory may be tuple (default) or dict (dict_row)
        if isinstance(row, dict):
            # information_schema EXISTS result column name is usually "exists"
            return bool(row.get("exists", next(iter(row.values()))))
        return bool(row[0])


def _pick_keyset_columns(conn) -> tuple[str, str]:
    """
    Choose a stable 2-column ordering for keyset pagination.
    Preference: (tst, id) then (tst, created_at) then (created_at, id).
    """
    has_id = _has_column(conn, schema="public", table="locations", column="id")
    has_tst = _has_column(conn, schema="public", table="locations", column="tst")
    has_created_at = _has_column(conn, schema="public", table="locations", column="created_at")

    if has_tst and has_id:
        return ("tst", "id")
    if has_tst and has_created_at:
        return ("tst", "created_at")
    if has_created_at and has_id:
        return ("created_at", "id")

    raise RuntimeError(
        "Cannot paginate locations: need two stable columns among (tst, id, created_at). "
        "Found: "
        f"tst={has_tst}, id={has_id}, created_at={has_created_at}"
    )


def fetch_locations_page(
    conn,
    *,
    limit: int,
    key1: str,
    key2: str,
    last_key: tuple[object, object] | None,
    descending: bool,
):
    """
    Keyset pagination over public.locations with a stable 2-column ordering.
    """
    op = "<" if descending else ">"
    direction = "DESC" if descending else "ASC"

    where_keyset = ""
    params: dict[str, object] = {"limit": limit}
    if last_key is not None:
        where_keyset = f" AND ({key1}, {key2}) {op} (%(k1)s, %(k2)s) "
        params["k1"] = last_key[0]
        params["k2"] = last_key[1]

    q = f"""
        SELECT *
        FROM public.locations
        WHERE lat IS NOT NULL AND lon IS NOT NULL
        {where_keyset}
        ORDER BY {key1} {direction}, {key2} {direction}
        LIMIT %(limit)s
    """
    with conn.cursor() as cur:
        cur.execute(q, params)
        return cur.fetchall()


def location_row_to_points_insert(row: dict, *, user_id: int | None):
    lat = row.get("lat")
    lon = row.get("lon")
    if lat is None or lon is None:
        return None

    mapped_cols = {
        "lat",
        "lon",
        "bs",
        "batt",
        "tid",
        "topic",
        "alt",
        "vel",
        "t",
        "bssid",
        "ssid",
        "conn",
        "vac",
        "acc",
        "tst",
        "m",
        "inrids",
        "inregions",
        "cog",
        "tag",
        "created_at",
        "updated_at",
        "_type",
    }

    excluded_from_geodata = {"tag", "created_at", "updated_at", "_type"}

    raw_data = {k: _jsonable(v) for k, v in row.items()}

    geodata = {}
    for k, v in row.items():
        if k in mapped_cols:
            continue
        if k in excluded_from_geodata:
            continue
        geodata[k] = _jsonable(v)

    topic = row.get("topic") or ""
    tag = row.get("tag")
    if tag:
        topic = f"{topic}__{tag}" if topic else str(tag)

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    created_at = _to_naive_utc_timestamp(row.get("created_at"), now_utc)
    updated_at = _to_naive_utc_timestamp(row.get("updated_at"), now_utc)

    lon_f = _safe_float(lon)
    lat_f = _safe_float(lat)

    return {
        "battery_status": _safe_int(row.get("bs")),
        "ping": None,
        "battery": _safe_int(row.get("batt")),
        "tracker_id": row.get("tid"),
        "topic": topic if topic else None,
        "altitude": _safe_int(row.get("alt")),
        "longitude": lon,
        "velocity": row.get("vel"),
        "trigger": _safe_int(row.get("t")),
        "bssid": row.get("bssid"),
        "ssid": row.get("ssid"),
        "connection": _safe_int(row.get("conn")),
        "vertical_accuracy": _safe_int(row.get("vac")),
        "accuracy": _safe_int(row.get("acc")),
        "timestamp": _safe_int(row.get("tst")),
        "latitude": lat,
        "mode": _safe_int(row.get("m")),
        "inrids": row.get("inrids") or [],
        "in_regions": row.get("inregions") or [],
        "raw_data": raw_data,
        "geodata": geodata,
        "created_at": created_at,
        "updated_at": updated_at,
        "import_id": None,
        "city": None,
        "country": None,
        "user_id": user_id,
        "visit_id": None,
        "reverse_geocoded_at": None,
        "course": _safe_float(row.get("cog")),
        "course_accuracy": None,
        "external_track_id": None,
        "country_id": None,
        "track_id": None,
        "country_name": None,
        "lon_f": lon_f,
        "lat_f": lat_f,
    }


def _chunked(seq, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def insert_points(conn, points_rows: list[dict], *, dry_run: bool, batch_size: int):
    # No RETURNING: it slows inserts a lot; we report summary via counts.
    sql = """
        INSERT INTO public.points (
            battery_status, ping, battery, tracker_id, topic, altitude,
            longitude, velocity, trigger, bssid, ssid, connection,
            vertical_accuracy, accuracy, "timestamp", latitude, mode,
            inrids, in_regions, raw_data, import_id, city, country,
            created_at, updated_at, user_id, geodata, visit_id,
            reverse_geocoded_at, course, course_accuracy, external_track_id,
            lonlat, country_id, track_id, country_name
        )
        VALUES (
            %(battery_status)s, %(ping)s, %(battery)s, %(tracker_id)s, %(topic)s, %(altitude)s,
            %(longitude)s, %(velocity)s, %(trigger)s, %(bssid)s, %(ssid)s, %(connection)s,
            %(vertical_accuracy)s, %(accuracy)s, %(timestamp)s, %(latitude)s, %(mode)s,
            %(inrids)s, %(in_regions)s, %(raw_data)s, %(import_id)s, %(city)s, %(country)s,
            %(created_at)s, %(updated_at)s, %(user_id)s, %(geodata)s, %(visit_id)s,
            %(reverse_geocoded_at)s, %(course)s, %(course_accuracy)s, %(external_track_id)s,
            CASE
                WHEN %(lon_f)s IS NULL OR %(lat_f)s IS NULL THEN NULL
                ELSE ST_SetSRID(ST_MakePoint(%(lon_f)s, %(lat_f)s), 4326)::geography
            END,
            %(country_id)s, %(track_id)s, %(country_name)s
        )
        ON CONFLICT (lonlat, "timestamp", user_id) DO NOTHING
    """

    if dry_run:
        print("DRY RUN: not inserting. First row payload preview:")
        if points_rows:
            preview = {k: v for k, v in points_rows[0].items() if k not in {"raw_data", "geodata"}}
            print(json.dumps(preview, default=str, indent=2))
        return

    total = len(points_rows)
    bar = None
    if tqdm is not None:
        bar = tqdm(total=total, desc="Inserting points", unit="row", dynamic_ncols=True)

    with conn.cursor() as cur:
        # Pipeline reduces client<->server roundtrips drastically vs 1 execute() per row.
        for batch in _chunked(points_rows, max(1, batch_size)):
            with conn.transaction():
                with conn.pipeline():
                    for row in batch:
                        payload = dict(row)
                        payload["raw_data"] = Jsonb(payload.get("raw_data", {}))
                        payload["geodata"] = Jsonb(payload.get("geodata", {}))
                        cur.execute(sql, payload)
                        if bar is not None:
                            bar.update(1)

    if bar is not None:
        bar.close()


def _count_points(conn, user_id: int | None) -> int | None:
    if user_id is None:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM public.points WHERE user_id = %s", (user_id,))
        return int(cur.fetchone()[0])


def main():
    parser = argparse.ArgumentParser(
        description="Copy Supabase locations into Dawarich points (default: FIRST/oldest; use --last for newest)."
    )

    # Supabase source
    parser.add_argument("--secrets", default=DEFAULT_SECRETS_FILE, help="Path to secrets.json")
    parser.add_argument("--pooler-host", default=DEFAULT_POOLER_HOST, help="Supabase pooler host")
    parser.add_argument("--limit", type=int, default=1000, help="How many rows to insert")
    parser.add_argument("--last", action="store_true", help="Insert LAST (newest) rows instead of FIRST (oldest)")
    parser.add_argument("--all", action="store_true", help="Insert ALL rows (paged); ignores --limit")
    parser.add_argument("--page-size", type=int, default=5000, help="Page size for --all mode")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=50_000,
        help="In --all mode, print progress every N fetched rows (set 0 to disable)",
    )

    # Local Dawarich target
    parser.add_argument("--dst-host", default=_env_first("DAWARICH_HOST", "DATABASE_HOST", default="localhost"))
    parser.add_argument("--dst-port", type=int, default=int(_env_first("DAWARICH_PORT", "DATABASE_PORT", default="5432")))
    parser.add_argument(
        "--dst-db",
        default=_env_first("DAWARICH_DB", "DATABASE_NAME", "POSTGRES_DB", default="dawarich_development"),
    )
    parser.add_argument(
        "--dst-user",
        default=_env_first("DAWARICH_USER", "DATABASE_USERNAME", "POSTGRES_USER", default="postgres"),
    )
    parser.add_argument(
        "--dst-password",
        default=_env_first("DAWARICH_PASSWORD", "DATABASE_PASSWORD", "POSTGRES_PASSWORD", default="password"),
    )
    parser.add_argument("--user-id", type=int, default=int(os.getenv("DAWARICH_POINTS_USER_ID", "0")) or None)
    parser.add_argument(
        "--allow-null-user-id",
        action="store_true",
        help="Allow inserting points with user_id NULL (NOT recommended; may allow duplicates).",
    )

    # Performance knobs
    parser.add_argument("--batch-size", type=int, default=1000, help="Commit every N rows (bigger = faster)")
    parser.add_argument("--dry-run", action="store_true", help="Print payload preview; do not insert")

    args = parser.parse_args()
    if args.user_id is None and not args.allow_null_user_id:
        print(
            "Error: --user-id is required for reliable dedupe (unique key is lonlat,timestamp,user_id). "
            "Pass --user-id (e.g. 1) or set DAWARICH_POINTS_USER_ID. "
            "If you really want NULL user_id, pass --allow-null-user-id."
        )
        sys.exit(2)

    supabase_url, supabase_password = load_supabase_config(args.secrets)
    project_ref = parse_project_ref(supabase_url)
    src_dsn = build_supabase_dsn(project_ref, supabase_password, args.pooler_host)

    dst_dsn = build_dawarich_dsn(args.dst_host, args.dst_port, args.dst_db, args.dst_user, args.dst_password)

    print(f"Source (Supabase): {args.pooler_host} / db={DEFAULT_DB_NAME} / user=postgres.{project_ref}")
    print(f"Destination (Dawarich): {args.dst_host}:{args.dst_port} / db={args.dst_db} / user={args.dst_user}")
    which = "LAST (newest)" if args.last else "FIRST (oldest)"
    print(f"Inserting {which} {args.limit} locations into public.points...")
    if args.user_id is not None:
        print(f"Setting inserted points.user_id = {args.user_id}")
    print(f"batch_size={args.batch_size}")

    with psycopg.connect(src_dsn, row_factory=dict_row) as src_conn:
        if args.all:
            key1, key2 = _pick_keyset_columns(src_conn)
            print(f"Importing ALL locations via keyset pagination on ({key1}, {key2}) ...")
            last_key = None
            total_fetched = 0
            total_prepared = 0
            total_skipped = 0
            next_progress_at = args.progress_every if args.progress_every and args.progress_every > 0 else None

            with psycopg.connect(dst_dsn) as dst_conn:
                before = _count_points(dst_conn, args.user_id) or 0
                inserted_total = 0

                while True:
                    page = fetch_locations_page(
                        src_conn,
                        limit=max(1, args.page_size),
                        key1=key1,
                        key2=key2,
                        last_key=last_key,
                        descending=bool(args.last),
                    )
                    if not page:
                        break

                    total_fetched += len(page)
                    last_key = (page[-1].get(key1), page[-1].get(key2))

                    points_rows = []
                    skipped = 0
                    for row in page:
                        ins = location_row_to_points_insert(row, user_id=args.user_id)
                        if ins is None:
                            skipped += 1
                            continue
                        points_rows.append(ins)

                    total_prepared += len(points_rows)
                    total_skipped += skipped

                    insert_points(dst_conn, points_rows, dry_run=args.dry_run, batch_size=args.batch_size)
                    # Accurate inserted count (handles ON CONFLICT DO NOTHING)
                    current = _count_points(dst_conn, args.user_id) or 0
                    inserted_total = current - before
                    while next_progress_at is not None and total_fetched >= next_progress_at:
                        milestone = next_progress_at
                        print(
                            f"Progress: fetched>={milestone} (now {total_fetched}) prepared={total_prepared} skipped={total_skipped} inserted={inserted_total} "
                            f"last_key={last_key}"
                        )
                        next_progress_at += args.progress_every

                    if args.dry_run:
                        print("Done (dry-run, stopped after first page).")
                        return

                after = _count_points(dst_conn, args.user_id) or 0

            print(f"Fetched {total_fetched} rows; prepared {total_prepared} inserts; skipped {total_skipped}.")

            if before is not None and after is not None:
                print(f"Done. points(user_id={args.user_id}) count: {before} -> {after} (delta={after - before})")
            else:
                print("Done.")
            return

        if args.last:
            locations = fetch_last_locations(src_conn, args.limit)
        else:
            locations = fetch_first_locations(src_conn, args.limit)

    if not locations:
        print("No locations returned (lat/lon non-null filter might exclude everything).")
        return

    points_rows = []
    skipped = 0
    for row in locations:
        ins = location_row_to_points_insert(row, user_id=args.user_id)
        if ins is None:
            skipped += 1
            continue
        points_rows.append(ins)

    print(f"Fetched {len(locations)} rows; prepared {len(points_rows)} inserts; skipped {skipped}.")

    with psycopg.connect(dst_dsn) as dst_conn:
        before = _count_points(dst_conn, args.user_id)
        insert_points(dst_conn, points_rows, dry_run=args.dry_run, batch_size=args.batch_size)
        after = _count_points(dst_conn, args.user_id)

    if args.dry_run:
        print("Done (dry-run).")
        return

    if before is not None and after is not None:
        print(f"Done. points(user_id={args.user_id}) count: {before} -> {after} (delta={after - before})")
    else:
        print("Done.")


if __name__ == "__main__":
    main()


