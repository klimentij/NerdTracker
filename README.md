# 🌍 NerdTracker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

> 🗺️ Your personal, privacy-focused location tracking system that you actually own!

## 🌟 Overview

NerdTracker is an open-source solution for digital nomads and location tracking enthusiasts who want complete control over their movement data. Built with privacy in mind, it leverages free-tier services to create a powerful, cost-effective tracking system.

### ✨ Key Features

- 📱 24/7 iPhone location tracking via OwnTracks
- 🗄️ Personal data ownership with Supabase storage
- 🎯 Real-time location sharing with friends
- 📊 Detailed tracking data (altitude, WiFi, speed)
- 🏷️ Trip tagging and categorization
- ⚙️ Customizable tracking parameters
- 💨 Fast, serverless architecture
- 💰 Completely free to run

## 🚀 Why NerdTracker?

While Google Timeline is sunsetting its web version and paid services offer limited functionality, NerdTracker provides:

- **Complete Data Ownership** - Your location data stays in your Supabase database
- **Cost Effectiveness** - Built entirely on free tiers of Supabase and Cloudflare
- **Privacy First** - No third-party tracking or data sharing
- **Customization** - Fine-tune tracking frequency and storage policies
- **Open Source** - Modify and extend as needed

## 🛠️ Prerequisites

1. 📱 **Mobile Device**
   - iPhone or Android with [OwnTracks](https://owntracks.org/) installed
   - Tested primarily with iPhone 11

2. ☁️ **Services**
   - [Cloudflare Account](https://cloudflare.com) (Free tier)
   - [Supabase Account](https://supabase.com) (Free tier)

## 🏃‍♂️ Getting Started

### 📱 1. Mobile Setup
1. Install [OwnTracks](https://owntracks.org/) on your mobile device
   - [iOS App Store](https://apps.apple.com/us/app/owntracks/id692424691)
   - [Android Play Store](https://play.google.com/store/apps/details?id=org.owntracks.android)

### ☁️ 2. Supabase Setup
1. Create a free Supabase account:
   - Sign up at [supabase.com/dashboard/sign-up](https://supabase.com/dashboard/sign-up)
   - Or [self-host Supabase](https://supabase.com/docs/guides/self-hosting) for complete privacy

2. Create New Project:
   - Go to [supabase.com/dashboard/projects](https://supabase.com/dashboard/projects)
   - Create new organization (or use existing)
   - Click "New Project"
   - Choose a name and password
   - Select the free tier and your preferred region
   - Keep default security settings (Data API with public schema enabled)
   - Wait for project initialization (usually 1-2 minutes)

3. Create Database Table:
   - Go to the SQL editor in your Supabase dashboard
   - Copy and paste the following SQL:
   ```sql
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
     "SSID" varchar,         -- SSID of the WiFi
     "BSSID" varchar,        -- BSSID of the WiFi
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
   ```
   - Click "Run" to execute the SQL commands

[Additional setup steps coming soon...]

## 🤝 Contributing

Contributions are what make the open source community amazing! Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

⭐️ If this project helped you, don't forget to give it a star!