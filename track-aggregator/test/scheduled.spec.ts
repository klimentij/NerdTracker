import { describe, it, expect, vi } from 'vitest';
import worker, { getNextMonthToArchive } from '../src/index';

function makeBucket(initial: Record<string,string> = {}) {
  return {
    store: { ...initial },
    async get(key: string) { return this.store[key] ? { body: new Response(this.store[key]).body } : null; },
    async put(key: string, value: any) { const text = await new Response(value).text(); this.store[key] = text; },
    async list() { return { objects: Object.keys(this.store).map(key => ({ key })) }; }
  } as unknown as R2Bucket;
}

const supabaseData = [{ tst: 1717132800 }];
vi.mock('@supabase/supabase-js', () => ({
  createClient: () => ({
    from() { return {
      select() { return this; },
      gte() { return this; },
      lte() { return this; },
      order() { return { then: (cb: any) => cb({ data: supabaseData, error: null }) }; }
    }; }
  })
}));

describe('scheduled', () => {
  it('writes archive when missing', async () => {
    const bucket = makeBucket();
    await worker.scheduled({} as ScheduledEvent, { HISTORY_BUCKET: bucket, SUPABASE_URL: '', SUPABASE_KEY: '' } as any);
    const { objects } = await bucket.list();
    expect(objects.length).toBe(1);
  });
});
