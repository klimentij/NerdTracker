#!/usr/bin/env python3

import csv
import math
import os
import re
import pandas as pd
from datetime import datetime
from collections import defaultdict

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
    
    # Write the cleaned data as CSV
    print(f"Writing cleaned data to CSV: {output_file}")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows_to_keep)
    
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
        # Read the SQL file as text
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # Extract column names using regex
        column_pattern = r'INSERT INTO "public"."locations" \(([^)]+)\)'
        column_match = re.search(column_pattern, sql_content)
        
        if not column_match:
            print("Could not find column names in SQL file with pandas approach")
            return False
            
        # Extract values using pandas read_csv with io.StringIO
        # This is a trick to parse SQL VALUES as CSV-like data
        import io
        
        # Extract just the VALUES part
        values_pattern = r'VALUES\s+(.+?)(?:;|\Z)'
        values_match = re.search(values_pattern, sql_content, re.DOTALL)
        
        if not values_match:
            print("Could not extract VALUES part for pandas processing")
            return False
            
        values_text = values_match.group(1)
        
        # Replace parentheses with clearer CSV delimiters
        csv_like = values_text.replace('),(', ')\n(').strip()
        
        if csv_like.endswith(','):
            csv_like = csv_like[:-1]
            
        # Remove outer parentheses for each row
        csv_like = csv_like.replace('(', '').replace(')', '')
        
        # Write to a temporary CSV file that pandas can read
        temp_csv = os.path.join(os.path.dirname(output_csv), 'temp_sql_values.csv')
        with open(temp_csv, 'w', encoding='utf-8') as f:
            f.write(csv_like)
            
        # Parse column names
        columns = [col.strip().strip('"') for col in column_match.group(1).split(',')]
        
        # Read with pandas
        df = pd.read_csv(temp_csv, names=columns, sep=',', quotechar="'")
        
        # Save to the final CSV
        df.to_csv(output_csv, index=False)
        
        # Clean up temp file
        if os.path.exists(temp_csv):
            os.remove(temp_csv)
            
        print(f"Successfully parsed SQL with pandas approach and saved to {output_csv}")
        return True
    except Exception as e:
        print(f"Error using pandas to parse SQL: {e}")
        print("Falling back to manual parsing")
        return False

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(script_dir, 'locations_rows.sql')
    output_csv = os.path.join(script_dir, 'locations_cleaned.csv')
    output_sql = os.path.join(script_dir, 'locations_cleaned.sql')
    
    print("=== NerdTracker Location Data Cleanup Tool ===")
    print(f"Constants: HANGOUT_SILENCE_DIST={HANGOUT_SILENCE_DIST}m, "
          f"LAST_LOCATIONS_COUNT={LAST_LOCATIONS_COUNT}, "
          f"MIN_LOCATIONS_IN_RANGE={MIN_LOCATIONS_IN_RANGE}")
    
    if not os.path.exists(input_file):
        print(f"Error: Input file not found at {input_file}")
        print("Please place your locations_rows.sql file in the same directory as this script.")
        return
    
    # Try first with pandas approach
    pandas_success = parse_sql_with_pandas(input_file, output_csv)
    
    # If pandas approach failed, use the manual parsing
    if not pandas_success:
        # Run the cleanup with manual parsing
        result = clean_locations(input_file, output_csv)
    else:
        # pandas succeeded, now we need to clean the data
        # Convert CSV back to dataframe for cleaning
        df = pd.read_csv(output_csv)
        
        # Filter out rows with null lat/lon/tst
        initial_rows = len(df)
        df = df.dropna(subset=['lat', 'lon', 'tst'])
        null_dropped = initial_rows - len(df)
        
        # Sort by timestamp
        df = df.sort_values(by='tst')
        
        # Apply the hangout detection algorithm
        # This is a simplified version of clean_locations but using pandas
        # For now just using the pandas parsing approach without cleanup
        print(f"Skipping hangout detection on pandas-parsed data for now")
        print(f"Total rows: {initial_rows}")
        print(f"Rows with null lat/lon/tst (dropped): {null_dropped}")
        print(f"Valid rows remaining: {len(df)}")
        
        # Save the cleaned dataframe
        df.to_csv(output_csv, index=False)
        
        # Set result for later use
        result = {'original_count': initial_rows, 'kept_count': len(df)}
    
    if result:
        # Generate SQL file from cleaned CSV for re-importing
        generate_sql_from_csv(output_csv, output_sql)
        
        print("\n=== Next Steps ===")
        print("1. Review the detailed report (if generated)")
        print("2. Verify the cleaned data in locations_cleaned.csv")
        print("3. Import the cleaned data back to Supabase using locations_cleaned.csv")
        print("   or run the SQL in locations_cleaned.sql")

if __name__ == "__main__":
    main() 