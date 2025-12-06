#!/bin/bash
set -e

# Configuration
SECRETS_FILE="app/secrets.json"
BACKUP_DIR="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# We use the pooler because the user environment (and likely GHA) is IPv4 only.
# Verified Region: US West 1
POOLER_HOST="aws-0-us-west-1.pooler.supabase.com"

# Check if secrets file exists
if [ ! -f "$SECRETS_FILE" ]; then
    echo "Error: Secrets file not found at $SECRETS_FILE"
    exit 1
fi

# Extract credentials
DB_PASSWORD=$(jq -r '.DB_PASSWORD // .AUTH_PASSWORD' "$SECRETS_FILE")
SUPABASE_URL=$(jq -r '.SUPABASE_URL' "$SECRETS_FILE")

if [ "$SUPABASE_URL" == "null" ] || [ "$DB_PASSWORD" == "null" ]; then
    echo "Error: Could not extract SUPABASE_URL or DB_PASSWORD from secrets file."
    exit 1
fi

# Parse Project Ref
PROJECT_REF=$(echo "$SUPABASE_URL" | sed 's/https:\/\///;s/.supabase.co//')
DB_USER="postgres.$PROJECT_REF"
DB_PORT="5432"
DB_NAME="postgres"

OUTPUT_FILE="$BACKUP_DIR/locations_backup_$TIMESTAMP.dump"
mkdir -p "$BACKUP_DIR"

echo "Starting backup for table 'locations'..."
echo "Region: US West 1 ($POOLER_HOST)"
echo "User: $DB_USER"

# Determine pg_dump binary
# We try to use the brew installed v15 if available for compatibility
if [ -f "/opt/homebrew/opt/postgresql@15/bin/pg_dump" ]; then
    PG_DUMP_CMD="/opt/homebrew/opt/postgresql@15/bin/pg_dump"
    echo "Using Postgres 15 pg_dump: $PG_DUMP_CMD"
else
    PG_DUMP_CMD="pg_dump"
    echo "Using default pg_dump: $(which pg_dump)"
fi

# Export password for pg_dump
export PGPASSWORD="$DB_PASSWORD"

# Run pg_dump
# -F c : Custom format (compressed)
# -v : Verbose
# -t locations : Only the locations table
# No acl/owner flags as we cannot guarantee mapping on restore
echo "Connecting to database..."
"$PG_DUMP_CMD" -h "$POOLER_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t locations -F c --no-owner --no-acl -f "$OUTPUT_FILE" -v

# Clear password
unset PGPASSWORD

echo "Backup completed successfully: $OUTPUT_FILE"
ls -lh "$OUTPUT_FILE"

# Determine pg_restore binary for reporting
if [ -f "/opt/homebrew/opt/postgresql@15/bin/pg_restore" ]; then
    PG_RESTORE_CMD="/opt/homebrew/opt/postgresql@15/bin/pg_restore"
else
    PG_RESTORE_CMD="pg_restore"
fi

# Count rows
echo "Verifying row count..."
ROW_COUNT=$("$PG_RESTORE_CMD" -f - "$OUTPUT_FILE" 2>/dev/null | grep "^[0-9]" | wc -l | tr -d ' ')
echo "Total rows backed up: $ROW_COUNT"
