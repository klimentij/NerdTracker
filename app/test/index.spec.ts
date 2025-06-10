// test/index.spec.ts
import { env, createExecutionContext, waitOnExecutionContext, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll, vi } from 'vitest';

// Supabase's client depends on '@supabase/node-fetch', which isn't available in
// the Cloudflare Workers test runtime. Stub it so the worker module loads.
vi.mock('@supabase/node-fetch', () => ({ default: fetch }));

let worker: any;

beforeAll(async () => {
  worker = (await import('../src/index')).default;
});

// For now, you'll need to do something like this to get a correctly-typed
// `Request` to pass to `worker.fetch()`.
const IncomingRequest = Request<unknown, IncomingRequestCfProperties>;

describe('Hello World worker', () => {
        it('returns login page without credentials', async () => {
                const request = new IncomingRequest('http://example.com');
                const ctx = createExecutionContext();
                const response = await worker.fetch(request, env, ctx);
                await waitOnExecutionContext(ctx);
                const text = await response.text();
                expect(text.includes('<title>Login</title>')).toBe(true);
        });

        it('integration fetch also shows login', async () => {
                const response = await SELF.fetch('https://example.com');
                const text = await response.text();
                expect(text.includes('<title>Login</title>')).toBe(true);
        });
});
