# NerdTracker Location Data Cleanup Tool

This tool cleans up redundant location data in your NerdTracker database by applying the same "hangout" detection logic that's implemented in the location-inserter service.

## Purpose

When your OwnTracks app continuously sends location updates while you're stationary, it can create hundreds or thousands of nearly identical records in your database. This tool identifies these "hangout" sequences and keeps only one record per hangout, dramatically reducing database size while preserving your movement history.

## How it Works

The script implements the exact same logic as your location-inserter service:

1. It looks at each location point and the next N points (where N is `LAST_LOCATIONS_COUNT`, default: 10)
2. It calculates distances between points using the Haversine formula (same as your TypeScript code)
3. It counts how many locations are within `HANGOUT_SILENCE_DIST` meters (default: 100m)
4. If at least `MIN_LOCATIONS_IN_RANGE` locations (default: 5) are within range, it considers this a "hangout"
5. For each hangout, it keeps only the first record and removes the rest

## Requirements

- Python 3.6+
- Required packages: `pandas`, `csv`, `math`, `os`, `datetime`, `collections`

You can install the required package with:
```
pip install pandas
```

## Instructions

1. Export your locations table from Supabase as a CSV file named `locations_rows.csv`
2. Place this CSV file in the same folder as the script
3. Run the script:
   ```
   python cleanup_locations.py
   ```
4. Review the generated `cleanup_report.txt` file for detailed statistics
5. Verify the cleaned data in `locations_cleaned.csv`
6. If satisfied, import the cleaned CSV back into your Supabase database

## Configuration

If you need to adjust the constants, edit these values at the top of the script:

```python
HANGOUT_SILENCE_DIST = 100  # In meters
LAST_LOCATIONS_COUNT = 10   # Number of locations to check
MIN_LOCATIONS_IN_RANGE = 5  # Minimum locations to be considered a hangout
```

## Exporting Data from Supabase

1. Go to your Supabase dashboard
2. Select your project
3. Go to Table Editor
4. Select the "locations" table
5. Click the "Export" button and choose CSV format
6. Save the file as `locations_rows.csv` in the same folder as this script

## Importing Cleaned Data Back to Supabase

After running the script and verifying the results:

1. Back up your original data (recommended)
2. Delete all rows from your locations table
3. Import the `locations_cleaned.csv` file using the Supabase Table Editor "Import" button

## Safety Features

The script includes several safety features:

- It never modifies your original CSV file
- It generates a detailed report of all changes
- It handles null values and invalid coordinates gracefully
- It includes timestamp information for all removed points

## Troubleshooting

If you encounter any issues:

1. Make sure your CSV file has the correct column names
2. Check that lat/lon/tst columns contain valid numeric values
3. For large files, ensure you have enough memory available
4. If the script fails, check the error message for details 