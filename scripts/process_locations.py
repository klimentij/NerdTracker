#!/usr/bin/env python3
import sys
import csv
import json
import math
from datetime import datetime, timezone

# Configuration
SPEED_THRESHOLD_KMH = 200  # km/h
MIN_FLIGHT_DURATION_MIN = 15
MIN_FLIGHT_DISTANCE_KM = 50

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) * math.sin(dlat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dlon/2) * math.sin(dlon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def parse_iso(iso_str):
    # Handle slight variations in ISO format if needed
    try:
        return datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    except ValueError:
        # Fallback for other formats if necessary
        return datetime.strptime(iso_str, "%Y-%m-%d %H:%M:%S%z")

def process(input_file):
    points = []
    
    # Reading CSV
    # Expected headers: id, lat, lon, timestamp, ... (adjust based on actual DB schema)
    # We will assume columns: id, latitude, longitude, created_at, tag (optional)
    print(f"Reading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Use tst (Unix epoch) if available, else created_at
                if row.get('tst') and row['tst'].strip():
                    ts = float(row['tst'])
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                else:
                    dt = parse_iso(row['created_at'])
                    ts = dt.timestamp()

                points.append({
                    'id': row.get('id'),
                    'lat': float(row['lat']),
                    'lon': float(row['lon']),
                    'alt': float(row.get('alt', 0) if row.get('alt') else 0),
                    'vel': float(row.get('vel', 0) if row.get('vel') else 0),
                    'time': dt,
                    'ts': ts,
                    'tag': row.get('tag', ''),
                    'raw': row 
                })
            except (ValueError, KeyError) as e:
                # print(f"Skipping row due to error: {e}")
                pass

    if not points:
        print("No points found!")
        return

    # Sort by time
    points.sort(key=lambda x: x['ts'])
    print(f"Processing {len(points)} points...")

    # Detection Logic
    trips_features = []
    flights_features = []

    # Simple segment builder
    current_mode = 'ground'
    segment_points = [points[0]]
    
    for i in range(1, len(points)):
        p1 = points[i-1]
        p2 = points[i]
        
        time_diff = (p2['ts'] - p1['ts']) / 3600.0 # hours
        dist_km = haversine_distance(p1['lat'], p1['lon'], p2['lat'], p2['lon'])
        
        speed = 0
        if time_diff > 0:
            speed = dist_km / time_diff
        
        # Check if we should switch mode or break segment
        # Heuristic: High speed -> Flight candidate
        is_flight_speed = speed > SPEED_THRESHOLD_KMH
        
        # Gap check: If large time gap, break segment
        if time_diff * 3600 > 7200: # gap > 2 hours
            # Flush current segment
            features = create_features(segment_points, current_mode)
            if current_mode == 'flight':
                flights_features.extend(features)
            else:
                trips_features.extend(features)
            
            segment_points = [p2]
            current_mode = 'flight' if is_flight_speed else 'ground'
            continue
            
        # Mode switch check
        if is_flight_speed and current_mode == 'ground':
             # End ground segment
             trips_features.extend(create_features(segment_points, 'ground'))
             segment_points = [p1, p2]
             current_mode = 'flight'
        elif not is_flight_speed and current_mode == 'flight':
             # End flight segment
             flights_features.extend(create_features(segment_points, 'flight'))
             segment_points = [p1, p2]
             current_mode = 'ground'
        else:
            segment_points.append(p2)

    # Flush last segment
    if segment_points:
         features = create_features(segment_points, current_mode)
         if current_mode == 'flight':
             flights_features.extend(features)
         else:
             trips_features.extend(features)

    # Post-process flights: Filter short/noise
    valid_flights = []
    # Could revert short 'flights' back to ground or discard?
    # For now, simplistic approach: only output if significant
    for f in flights_features:
        props = f['properties']
        if props['dist_km'] > MIN_FLIGHT_DISTANCE_KM and props['duration_min'] > MIN_FLIGHT_DURATION_MIN:
            valid_flights.append(f)
        else:
            # Reclassify as trip? Or just keep? 
            # Let's keep small fast bursts as trips to be safe
            f['properties']['mode'] = 'ground' 
            trips_features.append(f)

    # Save
    save_geojson('data/trips.geojson', trips_features)
    save_geojson('data/flights.geojson', valid_flights)

def create_features(segment_points, mode):
    # To reduce tile size, we might want to split long segments or simplify?
    # For now, create 1 LineString per segment
    if len(segment_points) < 2:
        return []

    coords = [[p['lon'], p['lat']] for p in segment_points]
    
    start_time = segment_points[0]['ts']
    end_time = segment_points[-1]['ts']
    duration_min = (end_time - start_time) / 60.0
    
    # Approx distance
    total_dist = 0
    for i in range(len(segment_points)-1):
         total_dist += haversine_distance(
             segment_points[i]['lat'], segment_points[i]['lon'],
             segment_points[i+1]['lat'], segment_points[i+1]['lon']
         )

    props = {
        'start_ts': int(start_time),
        'end_ts': int(end_time),
        'mode': mode,
        'tag': segment_points[0]['tag'], # inherit tag from first point
        'dist_km': round(total_dist, 2),
        'duration_min': round(duration_min, 1)
        # 'record_ids': ... (could be large)
    }

    feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coords
        },
        "properties": props
    }
    return [feature]

def save_geojson(filename, features):
    print(f"Writing {len(features)} features to {filename}")
    with open(filename, 'w') as f:
        json.dump({
            "type": "FeatureCollection",
            "features": features
        }, f)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ./process_locations.py <input_csv>")
        sys.exit(1)
    
    process(sys.argv[1])
