import { createClient } from '@supabase/supabase-js'

export interface Env {
  SUPABASE_URL: string;
  SUPABASE_KEY: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_KEY)

    const { data, error } = await supabase
      .from('locations')
      .select('lat,lon,acc,alt,vel,vac,batt,SSID,tag,topic,tid,tst')
      .order('tst', { ascending: false })
      .limit(10000)

    if (error) {
      console.error('Error fetching data from Supabase:', error)
      return new Response('Error fetching data', { status: 500 })
    }

    const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        <title>Location Tracker</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
        <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
        <style>
          body { margin: 0; padding: 0; }
          #map { height: 100vh; width: 100%; }
          .leaflet-popup-content {
            font-size: 14px;
            line-height: 1.6;
          }
          .leaflet-tooltip {
            font-size: 12px;
            line-height: 1.4;
          }
          #dateRange {
            position: absolute;
            top: 10px;
            left: 10px;
            z-index: 1000;
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 1px 5px rgba(0,0,0,0.65);
          }
        </style>
      </head>
      <body>
        <div id="dateRange">
          <input type="text" id="dateRangePicker" placeholder="Select date range">
        </div>
        <div id="map"></div>
        <script>
          const locations = ${JSON.stringify(data)};
          
          const map = L.map('map', {
            zoomControl: false
          }).setView([0, 0], 2);

          L.control.zoom({
            position: 'bottomright'
          }).addTo(map);

          L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          }).addTo(map);

          function formatTimestamp(timestamp) {
            const date = new Date(timestamp * 1000);
            return date.toLocaleString();
          }

          function getTimeSince(timestamp) {
            const now = new Date();
            const then = new Date(timestamp * 1000);
            const diff = Math.floor((now - then) / 1000);

            if (diff < 60) return \`\${diff} sec ago\`;
            if (diff < 3600) return \`\${Math.floor(diff / 60)} min ago\`;
            if (diff < 86400) return \`\${Math.floor(diff / 3600)} hr ago\`;
            return \`\${Math.floor(diff / 86400)} days ago\`;
          }

          function filterLocations(startDate, endDate) {
            // Ensure endDate includes the entire day
            const adjustedEndDate = new Date(endDate);
            adjustedEndDate.setHours(23, 59, 59, 999);

            return locations.filter(loc => {
              const locDate = new Date(loc.tst * 1000);
              return locDate >= startDate && locDate <= adjustedEndDate;
            });
          }

          let currentMarker;

          function updateMap(filteredLocations) {
            map.eachLayer(layer => {
              if (layer instanceof L.Circle || layer instanceof L.Polyline) {
                map.removeLayer(layer);
              }
            });

            if (filteredLocations.length > 0) {
              const trackPoints = filteredLocations.map(loc => [loc.lat, loc.lon]);
              L.polyline(trackPoints, {color: 'red', opacity: 0.6}).addTo(map);

              filteredLocations.forEach(loc => {
                L.circle([loc.lat, loc.lon], {
                  radius: 4,
                  fillColor: 'red',
                  color: 'red',
                  weight: 1,
                  opacity: 0.6,
                  fillOpacity: 0.6
                }).addTo(map).bindTooltip(\`
                  Time: \${formatTimestamp(loc.tst)}<br>
                  Coordinates: \${loc.lat}, \${loc.lon}<br>
                  Accuracy: \${loc.acc} meters<br>
                  Altitude: \${loc.alt} meters<br>
                  Velocity: \${loc.vel} km/h<br>
                  Vertical Accuracy: \${loc.vac} meters<br>
                  Battery: \${loc.batt}%<br>
                  SSID: \${loc.SSID || 'N/A'}<br>
                  Tag: \${loc.tag || 'N/A'}<br>
                  Topic: \${loc.topic || 'N/A'}<br>
                  TID: \${loc.tid || 'N/A'}
                \`, {
                  permanent: false,
                  direction: 'top'
                });
              });

              map.fitBounds(trackPoints);
            }

            // Always show and update the current location
            const latest = locations[0];
            if (!currentMarker) {
              currentMarker = L.marker([latest.lat, latest.lon]).addTo(map);
            } else {
              currentMarker.setLatLng([latest.lat, latest.lon]);
            }
            
            const popupContent = \`
              <b>Current location (\${getTimeSince(latest.tst)})</b><br>
              Time: \${formatTimestamp(latest.tst)}<br>
              Coordinates: \${latest.lat}, \${latest.lon}<br>
              Accuracy: \${latest.acc} meters<br>
              Altitude: \${latest.alt} meters<br>
              Velocity: \${latest.vel} km/h<br>
              Vertical Accuracy: \${latest.vac} meters<br>
              Battery: \${latest.batt}%<br>
              SSID: \${latest.SSID || 'N/A'}<br>
              Tag: \${latest.tag || 'N/A'}<br>
              Topic: \${latest.topic || 'N/A'}<br>
              TID: \${latest.tid || 'N/A'}
            \`;

            currentMarker.bindPopup(popupContent);
            
            setTimeout(() => {
              currentMarker.openPopup();
            }, 100);

            currentMarker.on('click', function() {
              this.openPopup();
            });
          }

          // Set default date range to today
          const now = new Date();
          now.setHours(23, 59, 59, 999); // Set to end of today
          const startOfToday = new Date(now);
          startOfToday.setHours(0, 0, 0, 0); // Set to start of today
          let startDate = startOfToday;
          let endDate = now;

          const dateRangePicker = flatpickr("#dateRangePicker", {
            mode: "range",
            defaultDate: [startDate, endDate],
            maxDate: "today",
            onChange: function(selectedDates) {
              if (selectedDates.length === 2) {
                startDate = selectedDates[0];
                endDate = selectedDates[1];
                const filteredLocations = filterLocations(startDate, endDate);
                updateMap(filteredLocations);
              }
            }
          });

          // Initial map update with default date range
          const initialFilteredLocations = filterLocations(startDate, endDate);
          updateMap(initialFilteredLocations);
        </script>
      </body>
    </html>
    `;

    return new Response(html, {
      headers: {
        'Content-Type': 'text/html',
      },
    });
  },
};