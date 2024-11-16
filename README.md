# 🌍 NerdTracker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)
[![Version](https://img.shields.io/badge/version-v0.1.0--beta-blue)](https://github.com/yourusername/nerdtracker/releases)

> Smartphone + free services = real-time tracking & location history for active people. Privacy-focused, you own your data!

## 📱 What's This?

NerdTracker turns your smartphone into a personal location tracking system that runs 24/7/365 in the background. Unlike temporary location sharing in messaging apps, it continuously records your movements and provides both real-time location and detailed movement history.

![NerdTracker Web Interface](web-ui.jpg)

### 🎯 Who Is This For?

- **Active People** who want to track all their movements, routes, and visited places
- **Digital Nomads** looking to maintain a detailed log of their travels
- **Privacy-Conscious Users** who want full control over their location data
- **Tech Enthusiasts** interested in self-hosting their location tracking solution
- **Outdoor Adventurers** wanting to record their activities and share location with family

### 💡 Why Use This?

- **Zero Cost** - Built entirely on free tiers of Supabase and Cloudflare
- **True Privacy** - Your data stays in your own database, no third parties involved
- **Always On** - Runs continuously in the background without interruptions
- **Battery Efficient** - Optimized for all-day tracking without draining your battery
- **Data Rich** - Captures detailed data including altitude, speed, WiFi connections, and more
- **Full Control** - Customize tracking frequency, accuracy, and data retention

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
   - Primary testing done on iPhone 11, but Android is supported

2. ☁️ **Required Accounts**
   - [Cloudflare Account](https://cloudflare.com) (Free tier)
   - [Supabase Account](https://supabase.com) (Free tier)

### 🔧 Development Environment Setup

> Note: This setup guide is written and tested for macOS but can be adapted for Linux or Windows systems.

1. Install nvm (Node Version Manager):
   ```bash
   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
   ```
   
   **If curl command fails or nvm not found:**
   ```bash
   # Install via Homebrew
   brew install node
   ```

2. Install Node.js:
   ```bash
   # If using nvm (restart terminal first):
   nvm install 23

   # If installed via Homebrew, skip this step
   ```

3. Verify installations:
   ```bash
   node -v
   npm -v
   ```

4. Install Wrangler CLI:
   ```bash
   npm install -g wrangler
   ```

5. Authenticate with Cloudflare:
   ```bash
   wrangler login
   ```

## 🚀 Setup Instructions

### 1. Project Setup
1. Clone this repository
2. Install dependencies from the root directory:
   ```bash
   npm install --prefix location-inserter
   npm install --prefix app
   ```

### 2. Supabase Configuration
1. Create a new Supabase project:
   - Go to [supabase.com/dashboard/projects](https://supabase.com/dashboard/projects)
   - Click "New Project"
   - Note down:
     - Project URL
     - `anon` public key (Settings -> API)

2. Create database table:
   - Go to SQL editor in Supabase dashboard
   - Execute the following SQL:
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

### 3. Application Configuration
1. Run the setup script:
   ```bash
   python3 setup.py
   ```
   - Enter your Supabase project URL and anon key when prompted
   - Save the generated passwords securely

### 4. Deploy Services
1. Deploy location ingestion service from root directory:
   ```bash
   npx wrangler secret bulk location-inserter/secrets.json --name location-inserter
   npm run deploy --prefix location-inserter
   ```
   Note the deployed URL (e.g., `https://location-inserter.your-name.workers.dev`)

2. Deploy web interface from root directory:
   ```bash
   npx wrangler secret bulk app/secrets.json --name tracker
   npm run deploy --prefix app
   ```

### 5. Configure OwnTracks
1. Install and open OwnTracks app on your phone
2. Go to Settings (click ⓘ icon)
3. Configure the following settings:
   - **TrackerID**: Your initials (e.g., "KS")
   - **DeviceID**: Descriptive device name (e.g., "Klim's iPhone")
   - **UserID**: Use "AUTH_USER" from location-inserter/secrets.json
   - **Password**: Use "AUTH_PASS" from location-inserter/secrets.json
   - **URL**: Your location-inserter URL (from deployment step)
   
4. Optional Settings:
   - **pubTopicBase**: Current trip name (will be added to every location)

5. Recommended GPS Settings (for high-accuracy permanent tracking):
   ```
   Mode: Move
   ignoreInaccurateLocations: 50
   locatorDisplacement: 80
   locatorInterval: 30
   positions: 10
   maxHistory: 0
   monitoring: -1
   downgrade: 0
   extended data: True
   ```

For more details on location tracking parameters, see the [OwnTracks Documentation](https://owntracks.org/booklet/features/location/).

### 🔒 Security Notes
- Store all passwords from setup.py output securely
- All endpoints use HTTPS encryption
- Authentication is required for all access
- Location data is stored only in your Supabase database

## 🤝 Contributing

Contributions are what make the open source community amazing! Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

⭐️ If this project helped you, don't forget to give it a star!