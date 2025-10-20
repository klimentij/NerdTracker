CREATE EXTENSION earthdistance CASCADE;

-- Create the table
create table if not exists locations (
  id serial primary key,  -- Unique identifier for each entry
  "lat" float8,           -- Latitude of the location
  "lon" float8,           -- Longitude of the location
  "acc" int,              -- Accuracy of the reported location in meters
  "alt" int,              -- Altitude above sea level in meters
  "vel" int,              -- Velocity in km/h
  "vac" int,              -- Vertical accuracy of the altitude in meters
  "p" float8,             -- Barometric pressure in kPa
  "cog" int,              -- Course over ground in degrees
  "rad" int,              -- Radius around the region in meters
  "tst" int8,             -- UNIX epoch timestamp of the location fix
  "created_at" int8,      -- Timestamp when the message is constructed
  "tag" varchar,          -- Custom tag
  "topic" varchar,        -- MQTT topic
  "_type" varchar,        -- Type of the payload
  "tid" varchar(2),       -- Tracker ID used to display the initials of a user
  "conn" varchar,         -- Internet connectivity status
  "batt" int,             -- Device battery level in percent
  "bs" int,               -- Battery status (0=unknown, 1=unplugged, 2=charging, 3=full)
  "w" boolean,            -- Indicates if the phone is connected to WiFi
  "o" boolean,            -- Indicates if the phone is offline
  "m" int,                -- Monitoring mode (1=significant, 2=move)
  "ssid" varchar,         -- SSID of the WiFi
  "bssid" varchar,        -- BSSID of the WiFi
  "inregions" text[],     -- List of regions the device is currently in
  "inrids" text[],        -- List of region IDs the device is currently in
  "desc" varchar,         -- Description (used for waypoints and transitions)
  "uuid" varchar,         -- UUID of the BLE Beacon
  "major" int,            -- Major number of the BLE Beacon
  "minor" int,            -- Minor number of the BLE Beacon
  "event" varchar,        -- Event that triggered the transition
  "wtst" int8,            -- Timestamp of waypoint creation
  "poi" varchar,          -- Point of interest name
  "r" varchar,            -- Response to a reportLocation cmd message
  "u" varchar,            -- Manual publish requested by the user
  "t" varchar,            -- Trigger for the location report
  "c" varchar,            -- Circular region enter/leave event
  "b" varchar,            -- Beacon region enter/leave event
  "face" text,            -- Base64 encoded PNG image for user icon
  "steps" int,            -- Steps walked with the device
  "from_epoch" int8,      -- Effective start of time period for steps
  "to_epoch" int8,        -- Effective end of time period for steps
  "data" text,            -- Encrypted and Base64 encoded original JSON message
  "request" varchar       -- Request type (e.g., "tour")
);

-- Add indexes
create index if not exists idx_locations_tid on locations(tid, tst);

-- Enable RLS
alter table locations enable row level security;

-- Drop existing policy if it exists
drop policy if exists "Enable insert access for all users" on "public"."locations";

-- Create policy for anonymous users to insert
create policy "Enable insert access for all users"
on "public"."locations"
for insert
to anon
with check (true);

-- Automatically detect if reporter stays in 1 place
CREATE VIEW locations_no_dups AS
SELECT *
FROM locations;

GRANT INSERT ON locations_no_dups TO anon;

CREATE OR REPLACE FUNCTION locations_no_dups_insert_trigger()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER  -- run with owner's privileges
AS $$
DECLARE
    RECENT_LOCATIONS_LIMIT CONSTANT INT := 10;
    MAX_PROXIMITY_METERS CONSTANT INT := 100;
    MIN_WITHIN_RANGE CONSTANT INT := 5;

    rec locations;
    most_recent_rec locations;
    result locations;
    within_range_cnt INT := 0;
    is_recent_location_in_range BOOLEAN := FALSE;

    is_close BOOLEAN;
BEGIN
    -- Select the last LAST_LOCATIONS_COUNT locations from the locations table
    -- Filter out NULL lat/lon records
    FOR rec IN
        SELECT *
        FROM locations loc
        WHERE loc.lat IS NOT NULL
            AND loc.lon IS NOT NULL
            AND loc.tst IS NOT NULL
            AND loc.tid = NEW.tid -- Original code doesn't check if recent points belong to the same device
        ORDER BY tst DESC
        LIMIT RECENT_LOCATIONS_LIMIT
    LOOP
        is_close := earth_distance(
            ll_to_earth(NEW.lat, NEW.lon),
            ll_to_earth(rec.lat, rec.lon)
        ) < MAX_PROXIMITY_METERS;

        -- Count all recent records that are within proximity
        IF is_close
        THEN
            within_range_cnt := within_range_cnt + 1;
        END IF;

        -- For the first (most recent) record only: record if it's within range
        IF most_recent_rec IS NULL
        THEN
            is_recent_location_in_range := is_close;
            most_recent_rec := rec;
        END IF;
    END LOOP;

    -- Check if we should update or insert
    -- 1. The most recent location must be valid (non-null lat/lon)
    -- 2. The most recent location must be within range
    -- 3. At least MIN_WITHIN_RANGE locations must be within the hangout distance
    IF is_recent_location_in_range AND (within_range_cnt >= MIN_WITHIN_RANGE)
    THEN
        NEW.id := most_recent_rec.id;

        DELETE FROM locations
        WHERE id = most_recent_rec.id;

        INSERT INTO locations
        SELECT NEW.*
        RETURNING * INTO result;
    ELSE
        NEW.id := nextval('locations_id_seq');

        INSERT INTO locations
        SELECT NEW.*
        RETURNING * INTO result;
    END IF;
    RETURN result;
END;
$$;

CREATE TRIGGER trg_locations_no_dups_insert_trigger
INSTEAD OF INSERT ON locations_no_dups
FOR EACH ROW
EXECUTE FUNCTION locations_no_dups_insert_trigger();


CREATE OR REPLACE FUNCTION insert_or_update_location_json(new_loc_json json)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER  -- run with owner's privileges
AS $$
DECLARE
    new_loc locations;
BEGIN
    -- Populate the record from JSON
    SELECT * INTO new_loc
    FROM json_populate_record(NULL::locations, new_loc_json);

    INSERT INTO locations_no_dups
    SELECT new_loc.*;
END;
$$;
