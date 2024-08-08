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
			
			// Initialize Supabase client
			const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_KEY);

			// Select the last location from the locations table
			const { data: lastLocationData, error: selectError } = await supabase
				.from('locations')
				.select('*')
				.order('tst', { ascending: false })
				.limit(1);

			const lastLocation = lastLocationData?.[0];

			if (selectError) {
				console.error('Error selecting last location:', selectError);
			} else if (lastLocation) {
				// Check if it's the same WiFi
				const isSameWifi = body.conn === 'w' && lastLocation.conn === 'w' && 
					lastLocation.SSID && body.SSID && lastLocation.SSID === body.SSID;

				if (isSameWifi) {
					console.log('Updating last location (same WiFi)');
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