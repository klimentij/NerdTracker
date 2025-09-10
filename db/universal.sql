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
