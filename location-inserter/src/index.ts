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

			// Insert using triggerrable view to automatically handle hangouts
			const { data, error } = await supabase
						.from('locations_no_dups')
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
