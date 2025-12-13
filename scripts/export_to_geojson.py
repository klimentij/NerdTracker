#!/usr/bin/env python3
import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Try to import psycopg
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("Error: psycopg is required. Please install it:")
    print("  pip install psycopg[binary]")
    sys.exit(1)

# Default configuration
DEFAULT_POOLER_HOST = "aws-0-us-west-1.pooler.supabase.com"
DEFAULT_DB_NAME = "postgres"
SECRETS_FILE = "app/secrets.json"
OUTPUT_FILE = "backups/dawarich_import.json"

def load_config(secrets_path):
    path = Path(secrets_path)
    if not path.exists():
        print(f"Error: Secrets file not found at {path}")
        print("Please ensure you are running from the project root.")
        sys.exit(1)
        
    try:
        secrets = json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in {path}")
        sys.exit(1)

    supabase_url = secrets.get("SUPABASE_URL")
    # Try different password keys often used
    db_password = (
        secrets.get("DB_PASSWORD") or 
        secrets.get("AUTH_PASSWORD") or
        secrets.get("SUPABASE_DB_PASSWORD")
    )

    if not supabase_url:
        print("Error: SUPABASE_URL not found in secrets file.")
        sys.exit(1)
    if not db_password:
        print("Error: DB_PASSWORD (or AUTH_PASSWORD) not found in secrets file.")
        sys.exit(1)

    return supabase_url, db_password

def parse_project_ref(url):
    without_scheme = url.replace("https://", "").replace("http://", "")
    ref = without_scheme.split(".supabase.co")[0]
    return ref

def build_dsn(project_ref, password, pooler_host, port=5432):
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

def fetch_and_write_locations(dsn, out_path, limit=None):
    if limit:
        # Get last N records. To keep them chronological in the file, we can subquery or just export them.
        # Exporting in reverse chronological (newest first) is fine for most importers.
        print(f"Fetching last {limit} locations...")
        query = f"""
            SELECT *
            FROM public.locations
            WHERE lat IS NOT NULL AND lon IS NOT NULL
            ORDER BY tst DESC
            LIMIT {limit}
        """
    else:
        # Export all, oldest first
        query = """
            SELECT *
            FROM public.locations
            WHERE lat IS NOT NULL AND lon IS NOT NULL
            ORDER BY tst ASC
        """
    
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to database and preparing to write to {path}...")
    
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        # Use a named cursor for server-side streaming
        # Note: server-side cursors with LIMIT might behave differently depending on planner,
        # but for simple queries it's fine.
        with conn.cursor(name="geojson_export_cursor") as cur:
            print("Executing query (streaming)...")
            cur.execute(query)
            
            with open(path, 'w', encoding='utf-8') as f:
                # Write header
                f.write('{"type":"FeatureCollection","features":[')
                
                count = 0
                while True:
                    rows = cur.fetchmany(size=2000)
                    if not rows:
                        break
                    
                    for row in rows:
                        feat = row_to_feature(row)
                        if feat:
                            if count > 0:
                                f.write(',')
                            json.dump(feat, f, separators=(',', ':'))
                            count += 1
                            
                    print(f"Processed {count} records...", end='\r')

                # Write footer
                f.write(']}')
                print(f"\nFinished! Total records: {count}")


def row_to_feature(row):
    # Extract coordinates
    lat = row.get("lat")
    lon = row.get("lon")
    
    if lat is None or lon is None:
        return None
        
    # Helper for safe string conversion
    def safe_str(val, default):
        if val is None:
            return str(default)
        return str(val)

    # Helper for float string to match format like "-1.0"
    def safe_float_str(val, default):
        if val is None:
            v = default
        else:
            v = val
        try:
            return str(float(v))
        except (ValueError, TypeError):
            return str(default)

    # Map database columns to Dawarich export format properties
    # Explicitly mapped columns that go into specific properties
    mapped_cols = {
        'lat', 'lon', 'bs', 'batt', 'tid', 'topic', 'alt', 'vel', 't', 
        'bssid', 'ssid', 'conn', 'vac', 'acc', 'tst', 'm', 'inrids', 
        'inregions', 'cog'
    }
    
    # Collect all other fields into geodata to preserve full metadata
    # Note: tag, created_at, _type are excluded from both properties AND geodata
    # to avoid OwnTracks format detection (Dawarich checks for _type anywhere in properties)
    excluded_from_geodata = {'tag', 'created_at', '_type'}
    geodata = {}
    for k, v in row.items():
        if k not in mapped_cols and k not in excluded_from_geodata:
            if isinstance(v, datetime):
                geodata[k] = v.isoformat()
            else:
                geodata[k] = v

    # Build topic with tag appended if present
    topic = row.get("topic") or ""
    tag = row.get("tag")
    if tag:
        topic = f"{topic}__{tag}" if topic else tag
    
    props = {
        "battery_status": row.get("bs"),
        "ping": None,
        "battery": row.get("batt"),
        "tracker_id": row.get("tid"),
        "topic": topic if topic else None,
        "altitude": row.get("alt", 0) if row.get("alt") is not None else 0,
        "longitude": str(lon),
        "velocity": safe_str(row.get("vel"), -1),
        "trigger": row.get("t"),
        "bssid": row.get("bssid"),
        "ssid": row.get("ssid"),
        "connection": row.get("conn"),
        "vertical_accuracy": row.get("vac", 0) if row.get("vac") is not None else 0,
        "accuracy": row.get("acc", 0) if row.get("acc") is not None else 0,
        "timestamp": row.get("tst"),
        "latitude": str(lat),
        "mode": row.get("m"),
        "inrids": row.get("inrids") or [],
        "in_regions": row.get("inregions") or [],
        "city": None,
        "country": None,
        "geodata": geodata,
        "course": safe_float_str(row.get("cog"), -1.0),
        "course_accuracy": "-1.0",
        "external_track_id": None,
        "track_id": None,
        "country_name": None
    }

    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [float(lon), float(lat)]
        },
        "properties": props
    }

def main():
    parser = argparse.ArgumentParser(description="Export locations to GeoJSON for Dawarich import.")
    parser.add_argument("--secrets", default=SECRETS_FILE, help="Path to secrets.json")
    parser.add_argument("--output", default=OUTPUT_FILE, help="Output GeoJSON file path")
    parser.add_argument("--pooler-host", default=DEFAULT_POOLER_HOST, help="Supabase pooler host")
    parser.add_argument("--last", type=int, help="Export only the last N rows")
    
    args = parser.parse_args()
    
    # Adjust output filename if --last is used
    output_file = args.output
    if args.last:
        p = Path(output_file)
        stem = p.stem
        # Remove existing _last_N suffix if present (simple check)
        if "_last_" not in stem:
            new_name = f"{stem}_last_{args.last}{p.suffix}"
            output_file = p.parent / new_name

    # Load configuration
    supabase_url, db_password = load_config(args.secrets)
    project_ref = parse_project_ref(supabase_url)
    
    # Connect and fetch
    dsn = build_dsn(project_ref, db_password, args.pooler_host)
    try:
        fetch_and_write_locations(dsn, output_file, limit=args.last)
    except Exception as e:
        print(f"\nDatabase error: {e}")
        sys.exit(1)

    print(f"File saved to: {output_file}")
    print("This file is ready for Dawarich import.")

if __name__ == "__main__":
    main()

