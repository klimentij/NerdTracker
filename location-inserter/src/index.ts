import { createClient } from '@supabase/supabase-js'

interface Env {
  AUTH_USER: string;
  AUTH_PASS: string;
  SUPABASE_URL: string;
  SUPABASE_KEY: string;
}

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
			
			// Console log the prettified JSON body
			console.log('Received JSON body:');
			console.log(JSON.stringify(body, null, 2));
			
			// Initialize Supabase client
			const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_KEY);

			// Select the last location from the locations table
			const { data: lastLocation, error: selectError } = await supabase
				.from('locations')
				.select('lat, lon, tst, SSID, conn')
				.order('tst', { ascending: false })
				.limit(1)
				.single();

			if (selectError) {
				console.error('Error selecting last location:', selectError);
			} else if (lastLocation) {
				const distanceInMeters = calculateDistance(
					lastLocation.lat,
					lastLocation.lon,
					body.lat,
					body.lon
				);
				console.log(`Distance from last location: ${distanceInMeters} m`);

				// Check distance
				if (distanceInMeters < 100) {
					console.log('Skipping insertion: Distance < 100m');
					return new Response('Skipping insertion: Distance < 100m', { status: 200 });
				}

				// Check SSID only when connection type is 'w'
				if (body.conn === 'w' && lastLocation.conn === 'w' && 
					lastLocation.SSID && body.SSID && lastLocation.SSID === body.SSID) {
					console.log('Skipping insertion: Same non-null SSID on WiFi connection');
					return new Response('Skipping insertion: Same non-null SSID on WiFi connection', { status: 200 });
				}
			}

			// Insert the data into the locations table
			const { data, error } = await supabase
					.from('locations')
					.insert(body);

			if (error) {
				console.error('Error inserting data:', error);
				return new Response('Error inserting data', { status: 500 });
			}

			console.log('Data inserted successfully:', data);
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
	const R = 6371000; // Radius of the Earth in meters
	const φ1 = lat1 * Math.PI / 180;
	const φ2 = lat2 * Math.PI / 180;
	const Δφ = (lat2 - lat1) * Math.PI / 180;
	const Δλ = (lon2 - lon1) * Math.PI / 180;

	const a = Math.sin(Δφ/2) * Math.sin(Δφ/2) +
			  Math.cos(φ1) * Math.cos(φ2) *
			  Math.sin(Δλ/2) * Math.sin(Δλ/2);
	const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

	return R * c; // Distance in meters
}