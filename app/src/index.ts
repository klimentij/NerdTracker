import { createClient } from '@supabase/supabase-js'
import { DateTime } from 'luxon';
import { parse } from 'cookie';

export interface Env {
  SUPABASE_URL: string;
  SUPABASE_KEY: string;
  AUTH_USERNAME: string;
  AUTH_PASSWORD: string;
  JWT_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    
    // Check if the user is authenticated
    const cookie = request.headers.get('Cookie');
    const token = cookie ? parse(cookie).token : null;
    
    if (!token || !isValidToken(token, env.JWT_SECRET)) {
      const authHeader = request.headers.get('Authorization');
      if (!authHeader || !isAuthenticated(authHeader, env)) {
        return new Response(loginHtml, {
          headers: { 'WWW-Authenticate': 'Basic realm="Secure Area"', 'Content-Type': 'text/html' },
          status: 401
        });
      } else {
        // User authenticated via Basic Auth, set a cookie
        const newToken = generateToken(env.JWT_SECRET);
        const headers = new Headers({
          'Set-Cookie': `token=${newToken}; HttpOnly; Secure; SameSite=Strict; Path=/`,
          'Location': url.pathname + url.search
        });
        return new Response(null, { status: 302, headers });
      }
    }

    const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_KEY)

    let startDateTime = url.searchParams.get('start');
    let endDateTime = url.searchParams.get('end');
    const userTimezone = request.headers.get('X-User-Timezone') || 'UTC';

    // Convert start and end times to UTC
    if (startDateTime && endDateTime) {
      startDateTime = DateTime.fromISO(startDateTime, { zone: userTimezone }).toUTC().toISO();
      endDateTime = DateTime.fromISO(endDateTime, { zone: userTimezone }).toUTC().toISO();
    } else {
      const now = DateTime.now().setZone(userTimezone);
      startDateTime = now.startOf('day').toUTC().toISO();
      endDateTime = now.endOf('day').toUTC().toISO();
      
      // Update URL with default dates
      url.searchParams.set('start', startDateTime);
      url.searchParams.set('end', endDateTime);
      return Response.redirect(url.toString(), 302);
    }

    let allData = [];
    let error = null;

    console.log(`Fetching data for range: ${startDateTime} to ${endDateTime}`);

    if (startDateTime && endDateTime) {
      try {
        const start = new Date(startDateTime);
        const end = new Date(endDateTime);

        const startTimestamp = Math.floor(start.getTime() / 1000);
        const endTimestamp = Math.floor(end.getTime() / 1000);

        console.log(`Querying Supabase for tst range: ${startTimestamp} to ${endTimestamp}`);

        let page = 0;
        const pageSize = 1000;
        let hasMore = true;

        while (hasMore) {
          const { data: fetchedData, error: fetchError, count } = await supabase
            .from('locations')
            .select('lat,lon,acc,alt,vel,batt,SSID,tag,topic,tid,tst,conn', { count: 'exact' })
            .gte('tst', startTimestamp)
            .lte('tst', endTimestamp)
            .order('tst', { ascending: true })
            .range(page * pageSize, (page + 1) * pageSize - 1);

          if (fetchError) {
            console.error('Supabase query error:', fetchError);
            error = fetchError;
            break;
          }

          allData = allData.concat(fetchedData);
          console.log(`Fetched ${fetchedData.length} records from Supabase (page ${page + 1})`);

          if (fetchedData.length < pageSize || allData.length >= count) {
            hasMore = false;
          }

          page++;
        }

        console.log(`Total fetched records: ${allData.length}`);
      } catch (e) {
        console.error('Error in date processing or Supabase query:', e);
        error = e;
      }
    } else {
      console.log('No start or end date provided');
    }

    if (error) {
      console.error('Error fetching data from Supabase:', error)
      return new Response('Error fetching data', { status: 500 })
    }

    // Convert fetched data to user's timezone
    allData = allData.map(item => ({
      ...item,
      tst: DateTime.fromSeconds(item.tst).setZone(userTimezone).toISO(),
    }));

    // Check if it's an AJAX request
    const isAjax = request.headers.get('X-Requested-With') === 'XMLHttpRequest';

    if (isAjax) {
      // Return JSON data for AJAX requests
      return new Response(JSON.stringify(allData), {
        headers: { 'Content-Type': 'application/json' },
      });
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
        <script src="https://unpkg.com/leaflet-polylinedecorator/dist/leaflet.polylineDecorator.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/luxon@2.3.1/build/global/luxon.min.js"></script>
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
            display: flex;
            flex-direction: column;
          }
          #dateRange input {
            margin-bottom: 5px;
          }
          .leaflet-polylinedecorator-arrowhead {
            fill: none;
            stroke: red;
            stroke-width: 2;
            opacity: 0.6;
          }
        </style>
      </head>
      <body>
        <div id="dateRange">
          <input type="text" id="startDatePicker" placeholder="Start date and time">
          <input type="text" id="endDatePicker" placeholder="End date and time">
        </div>
        <div id="map"></div>
        <script>
          let locations = ${JSON.stringify(allData)};
          
          console.log('Initial locations data:', locations);

          const map = L.map('map', {
            zoomControl: false
          }).setView([0, 0], 2);

          L.control.zoom({
            position: 'bottomright'
          }).addTo(map);

          L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          }).addTo(map);

          // Detect user's timezone
          const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
          localStorage.setItem('userTimezone', userTimezone);

          function formatLocalDateTime(date) {
            return luxon.DateTime.fromJSDate(date).setZone(userTimezone).toFormat("yyyy-MM-dd'T'HH:mm:ss");
          }

          function convertToLocalTime(timestamp) {
            return luxon.DateTime.fromISO(timestamp).setZone(userTimezone).toLocaleString(luxon.DateTime.DATETIME_FULL);
          }

          function getTimeSince(isoTimestamp) {
            const now = luxon.DateTime.local();
            const then = luxon.DateTime.fromISO(isoTimestamp);
            const diff = now.diff(then, 'seconds').seconds;

            if (diff < 60) return \`\${Math.floor(diff)} sec ago\`;
            if (diff < 3600) return \`\${Math.floor(diff / 60)} min ago\`;
            if (diff < 86400) return \`\${Math.floor(diff / 3600)} hr ago\`;
            return \`\${Math.floor(diff / 86400)} days ago\`;
          }

          let currentMarker;
          let statsControl;

          function getConnectivityLabel(conn) {
            switch (conn) {
              case 'w': return 'Wi-Fi';
              case 'o': return 'Offline';
              case 'm': return 'Mobile Data';
              default: return 'Unknown';
            }
          }

          function updateMap(filteredLocations) {
            console.log('updateMap called with', filteredLocations.length, 'locations');

            // Clear existing layers
            map.eachLayer(layer => {
              if (layer instanceof L.Circle || layer instanceof L.Polyline || layer instanceof L.LayerGroup) {
                map.removeLayer(layer);
              }
            });

            // Remove the "No data available" message if it exists
            const noDataMessageContainer = document.querySelector('.no-data-message');
            if (noDataMessageContainer) {
              noDataMessageContainer.remove();
            }

            if (filteredLocations.length > 0) {
              console.log('First location:', filteredLocations[0]);
              console.log('Last location:', filteredLocations[filteredLocations.length - 1]);

              const trackPoints = filteredLocations.map(loc => {
                if (typeof loc.lat !== 'number' || typeof loc.lon !== 'number') {
                  console.error('Invalid location:', loc);
                  return null;
                }
                return [loc.lat, loc.lon];
              }).filter(point => point !== null);

              console.log('Valid track points:', trackPoints.length);

              if (trackPoints.length > 0) {
                const polyline = L.polyline(trackPoints, {color: 'red', opacity: 0.6}).addTo(map);
                console.log('Polyline added to map');
                const arrowDecorator = L.polylineDecorator(polyline, {
                  patterns: [
                    {
                      offset: 25,
                      repeat: 50,
                      symbol: L.Symbol.arrowHead({
                        pixelSize: 5,
                        polygon: false,
                        pathOptions: {
                          stroke: true,
                          weight: 2,
                          color: 'red',
                          opacity: 0.6
                        }
                      })
                    }
                  ]
                }).addTo(map);

                const trackGroup = L.layerGroup([polyline, arrowDecorator]).addTo(map);

                let totalDistance = 0;
                let totalSpeed = 0;
                let minAlt = Infinity;
                let maxAlt = -Infinity;

                for (let i = 1; i < filteredLocations.length; i++) {
                  const prev = filteredLocations[i - 1];
                  const curr = filteredLocations[i];
                  totalDistance += calculateDistance(prev.lat, prev.lon, curr.lat, curr.lon);
                  totalSpeed += curr.vel;
                  minAlt = Math.min(minAlt, curr.alt);
                  maxAlt = Math.max(maxAlt, curr.alt);
                }

                const avgSpeed = totalSpeed / filteredLocations.length;
                const numLocations = filteredLocations.length;

                filteredLocations.forEach((loc, index) => {
                  if (typeof loc.lat === 'number' && typeof loc.lon === 'number') {
                    const circle = L.circle([loc.lat, loc.lon], {
                      radius: 4,
                      fillColor: 'red',
                      color: 'red',
                      weight: 1,
                      opacity: 0.6,
                      fillOpacity: 0.6
                    }).addTo(map);
                    console.log(\`Added circle for location \${index}: \${loc.lat}, \${loc.lon}\`);
                    
                    circle.bindTooltip(\`
                      Time: \${convertToLocalTime(loc.tst)}<br>
                      Coordinates: \${loc.lat}, \${loc.lon}<br>
                      Accuracy: \${loc.acc} meters<br>
                      Altitude: \${loc.alt} meters<br>
                      Velocity: \${loc.vel !== null ? loc.vel : 0} km/h<br>
                      Battery: \${loc.batt}%<br>
                      Wi-Fi: \${loc.SSID ? loc.SSID : 'Not connected'}<br>
                      Connectivity: \${getConnectivityLabel(loc.conn)}<br>
                      Tag: \${loc.tag || 'N/A'}<br>
                      Topic: \${loc.topic || 'N/A'}<br>
                      TID: \${loc.tid || 'N/A'}
                    \`, {
                      permanent: false,
                      direction: 'top'
                    });
                  } else {
                    console.error('Invalid location:', loc);
                  }
                });

                if (statsControl) {
                  map.removeControl(statsControl);
                }
                statsControl = L.control({position: 'bottomleft'});
                statsControl.onAdd = function(map) {
                  const div = L.DomUtil.create('div', 'info legend');
                  div.innerHTML = 
                    '<h4>Track Statistics</h4>' +
                    '<p>Total Distance: ' + totalDistance.toFixed(2) + ' km</p>' +
                    '<p>Average Speed: ' + avgSpeed.toFixed(2) + ' km/h</p>' +
                    '<p>Number of Locations: ' + numLocations + '</p>' +
                    '<p>Min Altitude: ' + minAlt.toFixed(2) + ' m</p>' +
                    '<p>Max Altitude: ' + maxAlt.toFixed(2) + ' m</p>';
                  div.style.backgroundColor = 'white';
                  div.style.padding = '10px';
                  div.style.borderRadius = '5px';
                  div.style.boxShadow = '0 1px 5px rgba(0,0,0,0.65)';
                  div.style.maxWidth = '200px';
                  div.style.overflowY = 'auto';
                  div.style.maxHeight = '30vh';
                  return div;
                };
                statsControl.addTo(map);

                console.log('Fitting bounds to track points');
                map.fitBounds(trackPoints);
              } else {
                console.error('No valid track points found');
              }
            } else {
              console.log('No data available for the selected date range');
              const noDataMessage = L.control({position: 'topright'});
              noDataMessage.onAdd = function(map) {
                const div = L.DomUtil.create('div', 'info no-data-message');
                div.innerHTML = '<strong>No data available for the selected date range.</strong>';
                div.style.backgroundColor = 'white';
                div.style.padding = '10px';
                div.style.borderRadius = '5px';
                div.style.boxShadow = '0 1px 5px rgba(0,0,0,0.65)';
                return div;
              };
              noDataMessage.addTo(map);
            }

            const latest = filteredLocations[filteredLocations.length - 1];
            if (latest) {
              if (!currentMarker) {
                currentMarker = L.marker([latest.lat, latest.lon]).addTo(map);
              } else {
                currentMarker.setLatLng([latest.lat, latest.lon]);
              }
              
              const popupContent = '<b>Current location (' + getTimeSince(latest.tst) + ')</b><br>' +
                'Time: ' + convertToLocalTime(latest.tst) + '<br>' +
                'Coordinates: ' + latest.lat + ', ' + latest.lon + '<br>' +
                'Accuracy: ' + latest.acc + ' meters<br>' +
                'Altitude: ' + latest.alt + ' meters<br>' +
                'Velocity: ' + (latest.vel !== null ? latest.vel : 0) + ' km/h<br>' +
                'Battery: ' + latest.batt + '%<br>' +
                'Wi-Fi: ' + (latest.SSID ? latest.SSID : 'Not connected') + '<br>' +
                'Connectivity: ' + getConnectivityLabel(latest.conn) + '<br>' +
                'Tag: ' + (latest.tag || 'N/A') + '<br>' +
                'Topic: ' + (latest.topic || 'N/A') + '<br>' +
                'TID: ' + (latest.tid || 'N/A');

              currentMarker.bindPopup(popupContent);
              
              setTimeout(() => {
                currentMarker.openPopup();
              }, 100);

              currentMarker.on('click', function() {
                this.openPopup();
              });
            }
          }

          function calculateDistance(lat1, lon1, lat2, lon2) {
            const R = 6371;
            const dLat = (lat2 - lat1) * Math.PI / 180;
            const dLon = (lon2 - lon1) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                      Math.sin(dLon/2) * Math.sin(dLon/2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            return R * c;
          }

          function updateURLParams(start, end) {
            const params = new URLSearchParams(window.location.search);
            params.set('start', formatLocalDateTime(start));
            params.set('end', formatLocalDateTime(end));
            window.history.replaceState({}, '', \`\${window.location.pathname}?\${params}\`);
          }

          async function fetchLocations(start, end) {
            const userTimezone = localStorage.getItem('userTimezone') || 'UTC';
            const startUTC = luxon.DateTime.fromJSDate(start).setZone(userTimezone).toUTC().toISO();
            const endUTC = luxon.DateTime.fromJSDate(end).setZone(userTimezone).toUTC().toISO();
            
            updateURLParams(start, end);
            console.log('Fetching locations for range:', start, 'to', end);
            try {
              const response = await fetch(\`?start=\${startUTC}&end=\${endUTC}\`, {
                headers: {
                  'X-Requested-With': 'XMLHttpRequest',
                  'X-User-Timezone': userTimezone
                }
              });
              if (response.ok) {
                const newLocations = await response.json();
                console.log('Fetched locations:', newLocations);
                locations = newLocations.map(loc => ({
                  ...loc,
                  tst: loc.tst // Keep as ISO string, don't convert to Date
                }));
                updateMap(locations);
              } else {
                console.error('Failed to fetch locations, status:', response.status);
                updateMap([]);
              }
            } catch (error) {
              console.error('Error in fetchLocations:', error);
              updateMap([]);
            }
          }

          const urlParams = new URLSearchParams(window.location.search);
          const urlStartDate = urlParams.get('start');
          const urlEndDate = urlParams.get('end');
          
          let startDate, endDate;
          if (urlStartDate && urlEndDate) {
            startDate = luxon.DateTime.fromISO(urlStartDate).toJSDate();
            endDate = luxon.DateTime.fromISO(urlEndDate).toJSDate();
          } else {
            // Set start to 00:00 and end to 23:59 of the current day
            const now = luxon.DateTime.now().setZone(userTimezone);
            startDate = now.startOf('day').toJSDate();
            endDate = now.endOf('day').toJSDate();
          }

          const startDatePicker = flatpickr("#startDatePicker", {
            enableTime: true,
            defaultDate: startDate,
            dateFormat: "Y-m-d H:i",
            time_24hr: true,
            onChange: function(selectedDates) {
              if (selectedDates.length === 1) {
                startDate = selectedDates[0];
                fetchLocations(startDate, endDate);
              }
            }
          });

          const endDatePicker = flatpickr("#endDatePicker", {
            enableTime: true,
            defaultDate: endDate,
            dateFormat: "Y-m-d H:i",
            time_24hr: true,
            onChange: function(selectedDates) {
              if (selectedDates.length === 1) {
                endDate = selectedDates[0];
                fetchLocations(startDate, endDate);
              }
            }
          });

          // Ensure the date pickers are updated with the correct initial values
          startDatePicker.setDate(startDate, true);
          endDatePicker.setDate(endDate, true);

          console.log('Initial locations:', locations);
          if (locations && locations.length > 0) {
            console.log('Invoking initial updateMap');
            updateMap(locations);
          } else {
            console.log('No initial locations, fetching...');
            fetchLocations(startDate, endDate);
          }

          // Add this line to log any changes to the locations variable
          Object.defineProperty(window, 'locations', {
            set: function(newValue) {
              console.log('locations updated:', newValue);
              this._locations = newValue;
            },
            get: function() {
              return this._locations;
            }
          });
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
} as const;

function isAuthenticated(authHeader: string, env: Env): boolean {
  const [scheme, encoded] = authHeader.split(' ');

  if (!encoded || scheme !== 'Basic') {
    return false;
  }

  const buffer = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
  const decoded = new TextDecoder().decode(buffer).split(':');

  const username = decoded[0];
  const password = decoded[1];

  // Simple comparison instead of bcrypt
  return username === env.AUTH_USERNAME && password === env.AUTH_PASSWORD;
}

function generateToken(secret: string): string {
  // In a real-world scenario, use a proper JWT library
  // This is a simplified example
  const payload = {
    exp: Math.floor(Date.now() / 1000) + (10 * 365 * 24 * 60 * 60), // 10 years expiration
  };
  return btoa(JSON.stringify(payload)) + '.' + btoa(secret);
}

function isValidToken(token: string, secret: string): boolean {
  // In a real-world scenario, use a proper JWT library
  // This is a simplified example
  const [payloadBase64] = token.split('.');
  try {
    const payload = JSON.parse(atob(payloadBase64));
    return payload.exp > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

const loginHtml = `
<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8">
    <title>Login</title>
  </head>
  <body>
    <script>
      function showLoginPrompt() {
        const xhr = new XMLHttpRequest();
        xhr.open('GET', window.location.href, true);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.onreadystatechange = function() {
          if (xhr.readyState === 4) {
            if (xhr.status === 200 || xhr.status === 302) {
              window.location.reload();
            } else {
              showLoginPrompt();
            }
          }
        };
        xhr.send();
      }
      showLoginPrompt();
    </script>
  </body>
</html>
`;