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
      .limit(100)

    if (error) {
      console.error('Error fetching data from Supabase:', error)
      return new Response('Error fetching data', { status: 500 })
    }

    const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="UTF-8"/>
        <title>Location Tracker</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        <style>
          #map { height: 100vh; width: 100%; }
        </style>
      </head>
      <body>
        <div id="map"></div>
        <script>
          const locations = ${JSON.stringify(data)};
          
          const map = L.map('map').setView([0, 0], 2);

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

          if (locations.length > 0) {
            // Create a polyline for the track
            const trackPoints = locations.map(loc => [loc.lat, loc.lon]);
            L.polyline(trackPoints, {color: 'red', opacity: 0.6}).addTo(map);

            // Add circles for each point
            locations.forEach(loc => {
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

            // Add marker for the most recent location
            const latest = locations[0];
            L.marker([latest.lat, latest.lon])
              .addTo(map)
              .bindPopup(\`
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
              \`)
              .openPopup();

            // Fit the map to show all points
            map.fitBounds(trackPoints);
          }
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