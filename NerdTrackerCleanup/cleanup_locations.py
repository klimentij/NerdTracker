#!/usr/bin/env python3

import csv
import math
import os
import re
import pandas as pd
from datetime import datetime
from collections import defaultdict
import sys

# Schema types from README.md
FIELD_TYPES = {
    'id': 'int',
    'lat': 'float8',
    'lon': 'float8',
    'acc': 'int',
    'alt': 'int',
    'vel': 'int',
    'vac': 'int',
    'p': 'float8',
    'cog': 'int',
    'rad': 'int',
    'tst': 'int8',
    'created_at': 'int8',
    'tag': 'str',
    'topic': 'str',
    '_type': 'str',
    'tid': 'str',
    'conn': 'str',
    'batt': 'int',
    'bs': 'int',
    'w': 'bool',
    'o': 'bool',
    'm': 'int',
    'ssid': 'str',
    'bssid': 'str',
    'inregions': 'array',
    'inrids': 'array',
    'desc': 'str',
    'uuid': 'str',
    'major': 'int',
    'minor': 'int',
    'event': 'str',
    'wtst': 'int8',
    'poi': 'str',
    'r': 'str',
    'u': 'str',
    't': 'str',
    'c': 'str',
    'b': 'str',
    'face': 'str',
    'steps': 'int',
    'from_epoch': 'int8',
    'to_epoch': 'int8',
    'data': 'str',
    'request': 'str',
    'insert_time': 'timestamp'
}

def convert_value_to_type(value, field_type):
    """Convert a value to the correct type based on field_type"""
    if value is None or pd.isna(value) or value == '':
        return None
    
    try:
        if field_type in ['int', 'int8']:
            # Remove decimal part for integers if it's a string or float
            if isinstance(value, str) and '.' in value:
                return int(float(value))
            elif isinstance(value, float):
                return int(value)
            else:
                return int(value)
        elif field_type == 'float8':
            return float(value)
        elif field_type == 'bool':
            if isinstance(value, str):
                return value.lower() in ['true', 't', 'yes', 'y', '1']
            return bool(value)
        elif field_type == 'array':
            # Arrays are stored as comma-separated strings in CSV
            if isinstance(value, str):
                if value.startswith('{') and value.endswith('}'):
                    # PostgreSQL array format
                    return value
                else:
                    # Convert to PostgreSQL array format
                    items = [item.strip() for item in value.split(',')]
                    return '{' + ','.join(items) + '}'
            elif isinstance(value, list):
                return '{' + ','.join(str(item) for item in value) + '}'
            return value
        else:  # default to string
            return str(value)
    except Exception as e:
        print(f"Error converting {value} to {field_type}: {e}")
        return value  # Return original value if conversion fails

def apply_schema_types(row, field_types=FIELD_TYPES):
    """Apply schema types to a row of data"""
    typed_row = {}
    
    for key, value in row.items():
        if key in field_types:
            typed_row[key] = convert_value_to_type(value, field_types[key])
        else:
            typed_row[key] = value
            
    return typed_row

# Constants matching your location-inserter settings
HANGOUT_SILENCE_DIST = 100  # In meters, matching HANGOUT_SILENCE_DIST
LAST_LOCATIONS_COUNT = 10   # Matching LAST_LOCATIONS_COUNT
MIN_LOCATIONS_IN_RANGE = 5  # Minimum locations required to consider a hangout

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two points using Haversine formula
    Same implementation as in your TypeScript code
    Returns distance in meters
    """
    # Convert to numbers
    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
    except (ValueError, TypeError):
        print(f"Invalid coordinates: {lat1}, {lon1}, {lat2}, {lon2}")
        return float('inf')
    
    # Earth's radius in meters
    R = 6371e3
    
    # Convert degrees to radians
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    # Haversine formula
    a = (math.sin(delta_phi / 2) * math.sin(delta_phi / 2) +
         math.cos(phi1) * math.cos(phi2) *
         math.sin(delta_lambda / 2) * math.sin(delta_lambda / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c  # Distance in meters

def parse_sql_inserts(sql_file):
    """
    Parse SQL INSERT statements and extract data into a list of dictionaries
    """
    print(f"Reading SQL INSERT statements from: {sql_file}")
    
    # Read the SQL file
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # First extract column names from the INSERT statement
    column_pattern = r'INSERT INTO "public"."locations" \(([^)]+)\)'
    column_match = re.search(column_pattern, sql_content)
    
    if not column_match:
        raise ValueError("Could not find column names in SQL file")
    
    # Parse column names, removing quotes
    column_string = column_match.group(1)
    columns = [col.strip().strip('"') for col in column_string.split(',')]
    
    # Extract VALUES from the SQL
    values_pattern = r'VALUES\s+(\([^)]+\))(?:,\s*|\s*;)'
    values_matches = re.findall(values_pattern, sql_content)
    
    if not values_matches:
        raise ValueError("Could not find VALUES in SQL file")
    
    # Parse each row of values into a dictionary
    rows = []
    for values_str in values_matches:
        # Remove parentheses
        values_str = values_str.strip('()')
        
        # Split by commas but respect quoted strings
        values = []
        current = ''
        in_quotes = False
        quote_char = None
        
        for char in values_str:
            if char in ["'", '"']:
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
                current += char
            elif char == ',' and not in_quotes:
                values.append(current.strip())
                current = ''
            else:
                current += char
        
        if current:
            values.append(current.strip())
        
        # Create a dictionary for this row
        row = {}
        for i, col in enumerate(columns):
            if i < len(values):
                # Clean the value (remove quotes, handle NULL)
                value = values[i].strip()
                
                if value.lower() == 'null':
                    value = None
                elif (value.startswith("'") and value.endswith("'")) or \
                     (value.startswith('"') and value.endswith('"')):
                    value = value[1:-1]  # Remove quotes
                
                row[col] = value
            else:
                row[col] = None
        
        rows.append(row)
    
    print(f"Extracted {len(rows)} rows from SQL file")
    return columns, rows

def clean_locations(input_file, output_file):
    """
    Clean location data by removing redundant records
    Uses the same logic as the TypeScript code but works with SQL input files
    """
    # Parse the SQL file to get columns and data
    try:
        columns, rows = parse_sql_inserts(input_file)
    except Exception as e:
        print(f"Error parsing SQL file: {e}")
        return None
    
    # Filter out rows with null lat/lon/tst
    initial_rows = len(rows)
    rows = [row for row in rows if row.get('lat') and row.get('lon') and row.get('tst')]
    null_dropped = initial_rows - len(rows)
    
    # Sort by timestamp
    rows.sort(key=lambda x: float(x.get('tst', 0)))
    
    print(f"Total rows: {initial_rows}")
    print(f"Rows with null lat/lon/tst (dropped): {null_dropped}")
    print(f"Valid rows for processing: {len(rows)}")
    
    # Store original row count for reporting
    original_count = len(rows)
    
    # Track which rows to keep and which to remove
    rows_to_keep = []
    rows_to_remove = []
    processed_count = 0
    hangout_groups = 0
    
    # Process the rows using a sliding window approach
    i = 0
    while i < len(rows):
        current_row = rows[i]
        processed_count += 1
        
        # Look ahead to check next N locations
        window_size = min(LAST_LOCATIONS_COUNT, len(rows) - i - 1)
        
        if window_size < MIN_LOCATIONS_IN_RANGE - 1:
            # Not enough locations left to form a hangout group
            rows_to_keep.append(current_row)
            i += 1
            continue
        
        # Calculate distances to next locations
        distances = []
        for j in range(1, window_size + 1):
            if i + j < len(rows):
                next_row = rows[i + j]
                distance = calculate_distance(
                    current_row['lat'], current_row['lon'],
                    next_row['lat'], next_row['lon']
                )
                distances.append({
                    'index': i + j,
                    'distance': distance,
                    'within_range': distance <= HANGOUT_SILENCE_DIST
                })
        
        # Count how many locations are within range
        within_range_count = sum(1 for d in distances if d['within_range'])
        
        # Check if we have a hangout
        if within_range_count >= MIN_LOCATIONS_IN_RANGE:
            hangout_groups += 1
            # Keep the current row
            rows_to_keep.append(current_row)
            
            # Skip all locations in this hangout
            last_within_index = max([d['index'] for d in distances if d['within_range']], default=i)
            
            # Mark these rows as removed
            for j in range(i + 1, last_within_index + 1):
                if j < len(rows):
                    rows_to_remove.append(rows[j])
            
            # Move to the next location after this hangout
            i = last_within_index + 1
        else:
            # Not a hangout, keep this row and move to the next
            rows_to_keep.append(current_row)
            i += 1
    
    # Generate report
    removed_count = len(rows_to_remove)
    kept_count = len(rows_to_keep)
    
    # Group removed locations by date for better reporting
    removed_by_date = defaultdict(int)
    for row in rows_to_remove:
        try:
            date = datetime.fromtimestamp(float(row['tst'])).strftime('%Y-%m-%d')
            removed_by_date[date] += 1
        except (ValueError, TypeError):
            removed_by_date['unknown_date'] += 1
    
    # Write the cleaned data as CSV with proper types
    print(f"Writing cleaned data to CSV: {output_file}")
    
    # Apply schema types to each row
    typed_rows = [apply_schema_types(row) for row in rows_to_keep]
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()
        writer.writerows(typed_rows)
    
    # Write detailed report
    report_file = os.path.join(os.path.dirname(output_file), 'cleanup_report.txt')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=== NerdTracker Location Data Cleanup Report ===\n\n")
        f.write(f"Cleanup performed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Input file: {input_file}\n")
        f.write(f"Output file: {output_file}\n\n")
        
        f.write("=== Configuration ===\n")
        f.write(f"HANGOUT_SILENCE_DIST: {HANGOUT_SILENCE_DIST} meters\n")
        f.write(f"LAST_LOCATIONS_COUNT: {LAST_LOCATIONS_COUNT} locations\n")
        f.write(f"MIN_LOCATIONS_IN_RANGE: {MIN_LOCATIONS_IN_RANGE} locations\n\n")
        
        f.write("=== Summary Statistics ===\n")
        f.write(f"Total rows in original file: {initial_rows}\n")
        f.write(f"Rows with null lat/lon/tst (dropped): {null_dropped}\n")
        f.write(f"Valid rows for processing: {original_count}\n")
        f.write(f"Rows processed: {processed_count}\n")
        f.write(f"Hangout groups identified: {hangout_groups}\n")
        f.write(f"Rows kept: {kept_count} ({kept_count/original_count*100:.2f}%)\n")
        f.write(f"Rows removed: {removed_count} ({removed_count/original_count*100:.2f}%)\n\n")
        
        f.write("=== Removed Rows by Date ===\n")
        for date, count in sorted(removed_by_date.items()):
            f.write(f"{date}: {count} rows removed\n")
    
    print("\n=== Cleanup Summary ===")
    print(f"Total rows processed: {original_count}")
    print(f"Hangout groups identified: {hangout_groups}")
    print(f"Rows kept: {kept_count} ({kept_count/original_count*100:.2f}%)")
    print(f"Rows removed: {removed_count} ({removed_count/original_count*100:.2f}%)")
    print(f"\nDetailed report written to: {report_file}")
    print(f"Cleaned data written to: {output_file}")
    
    return {
        'original_count': original_count,
        'hangout_groups': hangout_groups,
        'kept_count': kept_count,
        'removed_count': removed_count,
        'report_file': report_file
    }

def generate_sql_from_csv(csv_file, output_sql_file):
    """
    Generate SQL INSERT statements from the cleaned CSV file for re-importing to Supabase
    """
    print(f"Generating SQL INSERT statements from CSV: {csv_file}")
    
    # Read the CSV file
    df = pd.read_csv(csv_file)
    
    # Get column names
    columns = df.columns.tolist()
    
    # Open output file
    with open(output_sql_file, 'w', encoding='utf-8') as f:
        # Write header
        column_str = ", ".join([f'"{col}"' for col in columns])
        f.write(f'INSERT INTO "public"."locations" ({column_str}) VALUES\n')
        
        # Write values
        rows = []
        for _, row in df.iterrows():
            values = []
            for col in columns:
                value = row[col]
                
                # Handle NULL values
                if pd.isna(value):
                    values.append('NULL')
                # Handle strings
                elif isinstance(value, str):
                    # Fix: Avoid backslashes in f-string expressions
                    escaped_value = value.replace("'", "''")
                    values.append(f"'{escaped_value}'")
                # Handle boolean
                elif isinstance(value, bool):
                    values.append('TRUE' if value else 'FALSE')
                # Handle other types (numbers)
                else:
                    values.append(str(value))
            
            rows.append(f"({', '.join(values)})")
        
        # Join rows with commas and add semicolon at the end
        f.write(',\n'.join(rows))
        f.write(';\n')
    
    print(f"SQL INSERT statements written to: {output_sql_file}")
    return output_sql_file

def parse_sql_with_pandas(sql_file, output_csv):
    """
    Alternative method to parse SQL dump files using pandas when possible
    """
    print(f"Attempting to parse SQL file with pandas: {sql_file}")
    
    try:
        # Check file size before processing
        file_size_mb = os.path.getsize(sql_file) / (1024 * 1024)
        print(f"SQL file size: {file_size_mb:.2f} MB")
        
        if file_size_mb > 100:
            print("Warning: Large SQL file detected. This might take some time or cause memory issues.")
            
        # Process file in chunks instead of reading it all at once
        print("Extracting column names...")
        columns = []
        with open(sql_file, 'r', encoding='utf-8') as f:
            # Read first 5000 chars to extract column names (should be enough)
            header = f.read(5000)
            column_pattern = r'INSERT INTO "public"."locations" \(([^)]+)\)'
            column_match = re.search(column_pattern, header)
            
            if not column_match:
                print("Could not find column names in SQL file header")
                return False
                
            column_string = column_match.group(1)
            columns = [col.strip().strip('"') for col in column_string.split(',')]
            print(f"Found {len(columns)} columns: {columns[:5]}...")
        
        # Use sqlite directly to parse the SQL file
        print("Trying to use pandas.read_sql_query approach...")
        try:
            import sqlite3
            
            # Create a temporary database
            temp_db = os.path.join(os.path.dirname(output_csv), 'temp_parse.db')
            if os.path.exists(temp_db):
                os.remove(temp_db)
                
            # Connect to the database
            conn = sqlite3.connect(temp_db)
            
            # Create a table matching the schema
            create_table_sql = f"CREATE TABLE locations ({', '.join([f'{col} TEXT' for col in columns])})"
            conn.execute(create_table_sql)
            
            # Read the SQL file and execute it
            print("Importing SQL data (this may take a while for large files)...")
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_dump = f.read()
                # Modify SQL to work with SQLite
                sql_dump = sql_dump.replace('"public"."locations"', 'locations')
                
                # Split into chunks and execute
                print("Executing SQL import...")
                conn.executescript(sql_dump)
                conn.commit()
                
            # Read the data with pandas
            print("Reading data into pandas DataFrame...")
            df = pd.read_sql_query("SELECT * FROM locations", conn)
            
            # Close connection and remove temp database
            conn.close()
            if os.path.exists(temp_db):
                os.remove(temp_db)
                
            # Save to CSV
            df.to_csv(output_csv, index=False)
            print(f"Successfully parsed SQL data with SQLite approach: {len(df)} rows")
            return True
            
        except Exception as sqlite_err:
            print(f"SQLite approach failed: {sqlite_err}")
            print("Trying alternative line-by-line parsing approach...")
        
        # If SQLite approach fails, try line-by-line parsing
        print("Starting line-by-line parsing...")
        output_lines = []
        with open(output_csv, 'w', encoding='utf-8') as outfile:
            # Write header
            outfile.write(','.join(columns) + '\n')
            
            # Process SQL file line by line
            row_count = 0
            with open(sql_file, 'r', encoding='utf-8') as f:
                current_values = ""
                parsing_values = False
                
                for i, line in enumerate(f):
                    if i % 1000 == 0:
                        print(f"Processing line {i}...")
                    
                    if 'VALUES' in line and not parsing_values:
                        parsing_values = True
                        # Extract the part after VALUES
                        current_values = line.split('VALUES')[1].strip()
                    elif parsing_values:
                        current_values += line
                    
                    # If we have a complete statement or end of file
                    if parsing_values and (');' in line or i == file_size_mb * 1000):  # Rough estimate
                        # Process VALUES and convert to CSV
                        values_pattern = r'\(([^)]+)\)'
                        matches = re.findall(values_pattern, current_values)
                        
                        for values_str in matches:
                            # Process and clean values
                            processed_values = []
                            in_quotes = False
                            quote_char = None
                            current = ''
                            
                            for char in values_str:
                                if char in ["'", '"']:
                                    if not in_quotes:
                                        in_quotes = True
                                        quote_char = char
                                    elif char == quote_char:
                                        in_quotes = False
                                        quote_char = None
                                    current += char
                                elif char == ',' and not in_quotes:
                                    # Clean the value
                                    value = current.strip()
                                    if value.lower() == 'null':
                                        processed_values.append('')
                                    elif (value.startswith("'") and value.endswith("'")) or \
                                        (value.startswith('"') and value.endswith('"')):
                                        processed_values.append(value[1:-1].replace('"', '""'))
                                    else:
                                        processed_values.append(value)
                                    current = ''
                                else:
                                    current += char
                            
                            # Add last value
                            if current:
                                value = current.strip()
                                if value.lower() == 'null':
                                    processed_values.append('')
                                elif (value.startswith("'") and value.endswith("'")) or \
                                    (value.startswith('"') and value.endswith('"')):
                                    processed_values.append(value[1:-1].replace('"', '""'))
                                else:
                                    processed_values.append(value)
                            
                            # Write CSV line
                            csv_line = ','.join([f'"{v}"' if ',' in v else v for v in processed_values])
                            outfile.write(csv_line + '\n')
                            row_count += 1
                        
                        # Reset for next VALUES block
                        current_values = ""
                        parsing_values = False
            
            print(f"Processed {row_count} rows")
        
        # Verify the CSV was created successfully
        if os.path.exists(output_csv) and os.path.getsize(output_csv) > 0:
            print(f"Successfully parsed SQL using line-by-line approach")
            return True
        else:
            print("Failed to create a valid CSV file")
            return False
            
    except Exception as e:
        print(f"Error using pandas to parse SQL: {e}")
        print("Falling back to manual parsing")
        import traceback
        traceback.print_exc()
        return False

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(script_dir, 'locations_rows.sql')
    output_csv = os.path.join(script_dir, 'locations_cleaned.csv')
    
    print("=== NerdTracker Location Data Cleanup Tool ===")
    print(f"Constants: HANGOUT_SILENCE_DIST={HANGOUT_SILENCE_DIST}m, "
          f"LAST_LOCATIONS_COUNT={LAST_LOCATIONS_COUNT}, "
          f"MIN_LOCATIONS_IN_RANGE={MIN_LOCATIONS_IN_RANGE}")
    
    if not os.path.exists(input_file):
        print(f"Error: Input file not found at {input_file}")
        print("Please place your locations_rows.sql file in the same directory as this script.")
        return
    
    print(f"Processing input file: {input_file}")
    
    # Check if the user wants to skip pandas approach
    use_pandas = True
    if len(sys.argv) > 1 and sys.argv[1].lower() == '--skip-pandas':
        print("Skipping pandas approach as requested")
        use_pandas = False
    
    # Try first with pandas approach unless skipped
    pandas_success = False
    if use_pandas:
        print("Trying pandas approach first...")
        pandas_success = parse_sql_with_pandas(input_file, output_csv)
    
    # If pandas approach failed or skipped, use the manual parsing
    if not pandas_success:
        print("Using manual parsing approach...")
        result = clean_locations(input_file, output_csv)
    else:
        # pandas succeeded, now we need to clean the data
        # Convert CSV back to dataframe for cleaning
        print("Pandas approach succeeded, now cleaning data with hangout detection...")
        try:
            df = pd.read_csv(output_csv, low_memory=False)
            
            # Filter out rows with null lat/lon/tst
            initial_rows = len(df)
            print(f"Initial rows from pandas: {initial_rows}")
            
            # Check if lat, lon, tst columns exist
            missing_cols = [col for col in ['lat', 'lon', 'tst'] if col not in df.columns]
            if missing_cols:
                print(f"Warning: Missing columns in pandas DataFrame: {missing_cols}")
                print("Columns in DataFrame:", df.columns.tolist())
                
                # Try to find alternative column names
                for col in missing_cols:
                    # Look for column names containing the missing column name
                    potential_cols = [c for c in df.columns if col.lower() in c.lower()]
                    if potential_cols:
                        print(f"Found potential matches for {col}: {potential_cols}")
                        # Rename the first matching column
                        df = df.rename(columns={potential_cols[0]: col})
            
            # Now try to clean the data
            # Drop rows with null lat/lon/tst
            df_filtered = df.dropna(subset=['lat', 'lon', 'tst'])
            null_dropped = initial_rows - len(df_filtered)
            
            # Sort by timestamp
            df_filtered = df_filtered.sort_values(by='tst')
            print(f"Total rows: {initial_rows}")
            print(f"Rows with null lat/lon/tst (dropped): {null_dropped}")
            print(f"Valid rows for processing: {len(df_filtered)}")
            
            # Convert lat/lon to float
            for col in ['lat', 'lon']:
                try:
                    df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce')
                except Exception as e:
                    print(f"Warning: Error converting {col} to numeric: {e}")
            
            # Apply hangout detection algorithm
            print("Applying hangout detection algorithm...")
            
            # Create a list for rows to keep
            rows_to_keep = []
            rows_to_remove = []
            processed_count = 0
            hangout_groups = 0
            
            # Process the rows using a sliding window approach (same as clean_locations)
            i = 0
            while i < len(df_filtered):
                current_row = df_filtered.iloc[i]
                processed_count += 1
                
                if processed_count % 1000 == 0:
                    print(f"Processed {processed_count}/{len(df_filtered)} rows, identified {hangout_groups} hangout groups...")
                
                # Look ahead to check next N locations
                window_size = min(LAST_LOCATIONS_COUNT, len(df_filtered) - i - 1)
                
                if window_size < MIN_LOCATIONS_IN_RANGE - 1:
                    # Not enough locations left to form a hangout group
                    rows_to_keep.append(current_row)
                    i += 1
                    continue
                
                # Calculate distances to next locations
                distances = []
                for j in range(1, window_size + 1):
                    if i + j < len(df_filtered):
                        next_row = df_filtered.iloc[i + j]
                        try:
                            distance = calculate_distance(
                                current_row['lat'], current_row['lon'],
                                next_row['lat'], next_row['lon']
                            )
                        except Exception as e:
                            # If there's an error calculating distance, assume it's far away
                            distance = float('inf')
                            
                        distances.append({
                            'index': i + j,
                            'distance': distance,
                            'within_range': distance <= HANGOUT_SILENCE_DIST
                        })
                
                # Count how many locations are within range
                within_range_count = sum(1 for d in distances if d['within_range'])
                
                # Check if we have a hangout
                if within_range_count >= MIN_LOCATIONS_IN_RANGE:
                    hangout_groups += 1
                    # Keep the current row
                    rows_to_keep.append(current_row)
                    
                    # Skip all locations in this hangout
                    last_within_index = max([d['index'] for d in distances if d['within_range']], default=i)
                    
                    # Mark these rows as removed
                    for j in range(i + 1, last_within_index + 1):
                        if j < len(df_filtered):
                            rows_to_remove.append(df_filtered.iloc[j])
                    
                    # Move to the next location after this hangout
                    i = last_within_index + 1
                else:
                    # Not a hangout, keep this row and move to the next
                    rows_to_keep.append(current_row)
                    i += 1
            
            # Convert rows_to_keep back to DataFrame
            df_cleaned = pd.DataFrame(rows_to_keep)
            
            # Apply schema types to all columns before saving
            print("Applying schema types to output data...")
            for col in df_cleaned.columns:
                if col in FIELD_TYPES:
                    field_type = FIELD_TYPES[col]
                    if field_type in ['int', 'int8']:
                        # For integer columns, first convert to float (to handle any decimal strings)
                        # then convert to int, then to string to avoid pandas adding .0
                        df_cleaned[col] = pd.to_numeric(df_cleaned[col], errors='coerce')
                        df_cleaned[col] = df_cleaned[col].astype('Int64')  # nullable integer type
                    elif field_type == 'float8':
                        df_cleaned[col] = pd.to_numeric(df_cleaned[col], errors='coerce')
                    elif field_type == 'bool':
                        df_cleaned[col] = df_cleaned[col].map(lambda x: True if x in [True, 'true', 'True', 't', 'yes', 'y', '1', 1] else False if x in [False, 'false', 'False', 'f', 'no', 'n', '0', 0] else None)
                    # No special handling needed for string columns
            
            # Generate report for pandas approach
            removed_count = len(rows_to_remove)
            kept_count = len(rows_to_keep)
            original_count = len(df_filtered)
            
            # Group removed locations by date for reporting
            removed_by_date = defaultdict(int)
            for row in rows_to_remove:
                try:
                    date = datetime.fromtimestamp(float(row['tst'])).strftime('%Y-%m-%d')
                    removed_by_date[date] += 1
                except (ValueError, TypeError):
                    removed_by_date['unknown_date'] += 1
            
            # Write detailed report
            report_file = os.path.join(os.path.dirname(output_csv), 'cleanup_report.txt')
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("=== NerdTracker Location Data Cleanup Report ===\n\n")
                f.write(f"Cleanup performed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"Input file: {input_file}\n")
                f.write(f"Output file: {output_csv}\n\n")
                f.write("Processed using pandas with hangout detection\n\n")
                
                f.write("=== Configuration ===\n")
                f.write(f"HANGOUT_SILENCE_DIST: {HANGOUT_SILENCE_DIST} meters\n")
                f.write(f"LAST_LOCATIONS_COUNT: {LAST_LOCATIONS_COUNT} locations\n")
                f.write(f"MIN_LOCATIONS_IN_RANGE: {MIN_LOCATIONS_IN_RANGE} locations\n\n")
                
                f.write("=== Summary Statistics ===\n")
                f.write(f"Total rows in original file: {initial_rows}\n")
                f.write(f"Rows with null lat/lon/tst (dropped): {null_dropped}\n")
                f.write(f"Valid rows for processing: {original_count}\n")
                f.write(f"Rows processed: {processed_count}\n")
                f.write(f"Hangout groups identified: {hangout_groups}\n")
                f.write(f"Rows kept: {kept_count} ({kept_count/original_count*100:.2f}%)\n")
                f.write(f"Rows removed: {removed_count} ({removed_count/original_count*100:.2f}%)\n\n")
                
                f.write("=== Removed Rows by Date ===\n")
                for date, count in sorted(removed_by_date.items()):
                    f.write(f"{date}: {count} rows removed\n")
            
            print("\n=== Cleanup Summary ===")
            print(f"Total rows processed: {original_count}")
            print(f"Hangout groups identified: {hangout_groups}")
            print(f"Rows kept: {kept_count} ({kept_count/original_count*100:.2f}%)")
            print(f"Rows removed: {removed_count} ({removed_count/original_count*100:.2f}%)")
            print(f"\nDetailed report written to: {report_file}")
            
            # Save the cleaned dataframe with correct types
            df_cleaned.to_csv(output_csv, index=False)
            print(f"Cleaned data written to: {output_csv}")
            
            # Set result for later use
            result = {
                'original_count': original_count,
                'hangout_groups': hangout_groups,
                'kept_count': kept_count,
                'removed_count': removed_count,
                'report_file': report_file
            }
            
        except Exception as e:
            print(f"Error during pandas cleaning: {e}")
            print("Falling back to manual parsing")
            import traceback
            traceback.print_exc()
            result = clean_locations(input_file, output_csv)
    
    print("\n=== Next Steps ===")
    print("1. Review the detailed report in cleanup_report.txt")
    print("2. Verify the cleaned data in locations_cleaned.csv")
    print("3. Import the cleaned data back to Supabase using locations_cleaned.csv")
    print("\nTo skip the pandas approach in the future, run: python cleanup_locations.py --skip-pandas")

if __name__ == "__main__":
    main() 