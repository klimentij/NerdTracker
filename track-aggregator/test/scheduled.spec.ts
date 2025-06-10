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
const mockSupabase = {
  from: vi.fn().mockReturnThis(),
  select: vi.fn().mockReturnThis(),
  gte: vi.fn().mockReturnThis(),
  lte: vi.fn().mockReturnThis(),
  order: vi.fn().mockResolvedValue({ data: supabaseData, error: null }),
};
vi.mock('@supabase/supabase-js', () => ({
  createClient: () => mockSupabase,
}));

describe('scheduled', () => {
  it('writes archive when missing', async () => {
    const bucket = makeBucket();
    await worker.scheduled({} as ScheduledController, { HISTORY_BUCKET: bucket, SUPABASE_URL: 'a', SUPABASE_KEY: 'b' });
    const { objects } = await bucket.list();
    expect(objects.length).toBe(1);
    const key = objects[0].key;
    expect(key).toMatch(/^\d{4}-\d{2}\.json\.gz$/);
  });
});

const base = new Date(Date.UTC(2025, 5, 15)); // June 2025

describe('getNextMonthToArchive', () => {
  it('returns previous month when none exist', () => {
    const next = getNextMonthToArchive([], base);
    expect(next?.toISOString().slice(0, 7)).toBe('2025-05');
  });

  it('skips existing months', () => {
    const next = getNextMonthToArchive(['2025-05.json.gz'], base);
    expect(next?.toISOString().slice(0, 7)).toBe('2025-04');
  });
});
