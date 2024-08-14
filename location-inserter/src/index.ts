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
			
			// Initialize Supabase client
			const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_KEY);

			// Select the last LAST_LOCATIONS_COUNT locations from the locations table
			const { data: lastLocationsData, error: selectError } = await supabase
				.from('locations')
				.select('*')
				.order('tst', { ascending: false })
				.limit(LAST_LOCATIONS_COUNT);

			if (selectError) {
				console.error('Error selecting last locations:', selectError);
				return new Response('Error selecting last locations', { status: 500 });
			}

			const lastLocation = lastLocationsData?.[0];

			if (lastLocation) {
				// Check if all distances are within HANGOUT_SILENCE_DIST
				const allWithinDistance = lastLocationsData.every(loc => 
					calculateDistance(body.lat, body.lon, loc.lat, loc.lon) <= HANGOUT_SILENCE_DIST
				);

				if (allWithinDistance) {
					console.log('Updating last location (within hangout distance)');
					const { data: updateData, error: updateError } = await supabase
						.from('locations')
						.update(body)
						.eq('tst', lastLocation.tst);

					if (updateError) {
						console.error('Error updating data:', updateError);
						return new Response('Error updating data', { status: 500 });
					}

					console.log('Data updated successfully');
					return new Response('Data updated successfully', { status: 200 });
				}
			}

			// If no update was needed, proceed with insertion
			const { data, error } = await supabase
						.from('locations')
						.insert(body);

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
	const R = 6371e3; // Earth's radius in meters
	const φ1 = lat1 * Math.PI / 180;
	const φ2 = lat2 * Math.PI / 180;
	const Δφ = (lat2 - lat1) * Math.PI / 180;
	const Δλ = (lon2 - lon1) * Math.PI / 180;

	const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
			  Math.cos(φ1) * Math.cos(φ2) *
			  Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
	const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

	return R * c; // Distance in meters
}