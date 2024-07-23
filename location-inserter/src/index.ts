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