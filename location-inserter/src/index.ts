import { createClient } from '@supabase/supabase-js'

interface Env {
  AUTH_USER: string;
  AUTH_PASS: string;
  SUPABASE_URL: string;
  SUPABASE_KEY: string;
}

// Maximum distance (in meters) between consecutive locations to be considered part of the same "hangout"
// If all of the last LAST_LOCATIONS_COUNT locations are within this distance, we update the last location instead of inserting a new one
const HANGOUT_SILENCE_DIST = 100;

// Number of recent locations to consider when determining if the user is in a "hangout"
const LAST_LOCATIONS_COUNT = 10;

// Minimum number of locations that need to be within distance to be considered a hangout
// This allows some outliers that might be due to GPS inaccuracy
const MIN_LOCATIONS_IN_RANGE = 5;

export default {
	async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
		// Check if the request method is POST
		if (request.method !== 'POST') {
			return new Response('Method Not Allowed', { status: 405 });
		}

		// Check Basic Authentication
		const authHeader = request.headers.get('Authorization');
		if (!authHeader || !isValidBasicAuth(authHeader, env)) {
			return new Response('Unauthorized', { 
				status: 401,
				headers: { 'WWW-Authenticate': 'Basic realm="User Visible Realm"' }
			});
		}

		try {
			// Parse the JSON body
			const body = await request.json();
			
			// Remove fields that are not in our schema
			const allowedFields = [
				'lat', 'lon', 'acc', 'alt', 'vel', 'vac', 'p', 'cog', 'rad', 'tst',
				'created_at', 'tag', 'topic', '_type', 'tid', 'conn', 'batt', 'bs',
				'w', 'o', 'm', 'ssid', 'bssid', 'inregions', 'inrids', 'desc',
				'uuid', 'major', 'minor', 'event', 'wtst', 'poi', 'r', 'u', 't',
				'c', 'b', 'face', 'steps', 'from_epoch', 'to_epoch', 'data', 'request'
			];

			// Type assertion to handle the unknown type from request.json()
			const typedBody = body as Record<string, any>;
			
			const cleanBody = Object.fromEntries(
				Object.entries(typedBody).filter(([key]) => allowedFields.includes(key))
			);
			
			// Initialize Supabase client
			const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_KEY);

			// Select the last LAST_LOCATIONS_COUNT locations from the locations table
			// Filter out NULL lat/lon records
			const { data: lastLocationsData, error: selectError } = await supabase
				.from('locations')
				.select('*')
				.not('lat', 'is', null)
				.not('lon', 'is', null)
				.not('tst', 'is', null)
				.order('tst', { ascending: false })
				.limit(LAST_LOCATIONS_COUNT);

			if (selectError) {
				console.error('Error selecting last locations:', selectError);
				return new Response('Error selecting last locations', { status: 500 });
			}

			// Log the count of valid records found
			console.log(`Found ${lastLocationsData?.length || 0} valid previous locations with non-null lat/lon`);
			
			const lastLocation = lastLocationsData?.[0];
			
			if (lastLocation && Array.isArray(lastLocationsData) && lastLocationsData.length > 0) {
				console.log(`Analyzing previous locations for hangout detection`);
				
				// Calculate distance for each location and log details
				const distances = lastLocationsData.map(loc => {
					const distance = calculateDistance(
						Number(cleanBody.lat), 
						Number(cleanBody.lon), 
						Number(loc.lat), 
						Number(loc.lon)
					);
					return { 
						id: loc.id, 
						tst: loc.tst, 
						distance: distance,
						isWithinRange: distance <= HANGOUT_SILENCE_DIST
					};
				});
				
				// Count how many are within range
				const withinRangeCount = distances.filter(d => d.isWithinRange).length;
				
				// Log distance details for debugging
				console.log(`New location: lat=${cleanBody.lat}, lon=${cleanBody.lon}`);
				console.log(`Last location: lat=${lastLocation.lat}, lon=${lastLocation.lon}`);
				console.log(`Distance to last location: ${distances[0].distance.toFixed(2)}m`);
				console.log(`Locations within ${HANGOUT_SILENCE_DIST}m range: ${withinRangeCount} out of ${distances.length}`);
				
				// Log the distances for the first few points
				const detailedLogging = distances.slice(0, 5).map(d => 
					`ID: ${d.id}, Distance: ${d.distance.toFixed(2)}m, Within range: ${d.isWithinRange}`
				);
				console.log("Detailed distances (first 5):", detailedLogging.join(" | "));
				
				// Check if we should update or insert
				// 1. The most recent location must be valid (non-null lat/lon)
				// 2. The most recent location must be within range
				// 3. At least MIN_LOCATIONS_IN_RANGE locations must be within the hangout distance
				const isRecentLocationInRange = distances[0]?.isWithinRange === true;
				const hasEnoughLocationsInRange = withinRangeCount >= MIN_LOCATIONS_IN_RANGE;
				
				// Log the decision criteria
				console.log(`Decision criteria: Recent location in range: ${isRecentLocationInRange}, Enough locations in range: ${hasEnoughLocationsInRange} (${withinRangeCount}/${MIN_LOCATIONS_IN_RANGE} needed)`);
				
				if (isRecentLocationInRange && hasEnoughLocationsInRange) {
					console.log(`Detected hangout: ${withinRangeCount} locations are within ${HANGOUT_SILENCE_DIST}m. Updating last location.`);
					
					// Use the ID for update instead of TST
					const { data: updateData, error: updateError } = await supabase
						.from('locations')
						.update(cleanBody)
						.eq('id', lastLocation.id);

					if (updateError) {
						console.error('Error updating data:', updateError);
						return new Response('Error updating data', { status: 500 });
					}

					console.log('Data updated successfully');
					return new Response('Data updated successfully', { status: 200 });
				} else {
					console.log(`Not a hangout: ${withinRangeCount}/${distances.length} locations within range. Inserting new location.`);
				}
			}

			// If no update was needed, proceed with insertion
			const { data, error } = await supabase
						.from('locations')
						.insert(cleanBody);

			if (error) {
				console.error('Error inserting data:', error);
				return new Response('Error inserting data', { status: 500 });
			}

			console.log('Data inserted successfully');
			return new Response('Data inserted successfully', { status: 200 });
		} catch (error) {
			// If there's an error parsing the JSON, return a 400 Bad Request
			return new Response('Invalid JSON', { status: 400 });
		}
	},
} satisfies ExportedHandler<Env>;

function isValidBasicAuth(authHeader: string, env: Env): boolean {
	const base64Credentials = authHeader.split(' ')[1];
	const credentials = atob(base64Credentials);
	const [username, password] = credentials.split(':');
	return username === env.AUTH_USER && password === env.AUTH_PASS;
}

function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
	// Ensure all inputs are numbers
	const numLat1 = Number(lat1);
	const numLon1 = Number(lon1);
	const numLat2 = Number(lat2);
	const numLon2 = Number(lon2);
	
	// Check if any values are NaN
	if (isNaN(numLat1) || isNaN(numLon1) || isNaN(numLat2) || isNaN(numLon2)) {
		console.error('Invalid coordinates for distance calculation:', { lat1, lon1, lat2, lon2 });
		return Infinity; // Return a large value to prevent hangout detection
	}
	
	const R = 6371e3; // Earth's radius in meters
	const φ1 = numLat1 * Math.PI / 180;
	const φ2 = numLat2 * Math.PI / 180;
	const Δφ = (numLat2 - numLat1) * Math.PI / 180;
	const Δλ = (numLon2 - numLon1) * Math.PI / 180;

	const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
			  Math.cos(φ1) * Math.cos(φ2) *
			  Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
	const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

	return R * c; // Distance in meters
}