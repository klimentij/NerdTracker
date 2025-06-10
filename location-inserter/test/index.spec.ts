// test/index.spec.ts
import { env, createExecutionContext, waitOnExecutionContext, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll, vi } from 'vitest';

vi.mock('@supabase/node-fetch', () => ({ default: fetch }));

let worker: any;

beforeAll(async () => {
  worker = (await import('../src/index')).default;
});

// For now, you'll need to do something like this to get a correctly-typed
// `Request` to pass to `worker.fetch()`.
const IncomingRequest = Request<unknown, IncomingRequestCfProperties>;

describe('inserter worker', () => {
        it('rejects unauthenticated requests', async () => {
                const request = new IncomingRequest('http://example.com', { method: 'POST' });
                const ctx = createExecutionContext();
                const response = await worker.fetch(request, env, ctx);
                await waitOnExecutionContext(ctx);
                expect(response.status).toBe(401);
        });

        it('GET requests not allowed', async () => {
                const response = await SELF.fetch('https://example.com');
                expect(response.status).toBe(405);
        });
});
