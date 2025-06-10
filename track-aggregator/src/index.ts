import { createClient } from '@supabase/supabase-js';

export function getNextMonthToArchive(keys: string[], now: Date): Date | null {
  const existing = new Set(keys.map(k => k.slice(0, 7))); // YYYY-MM
  // start with previous month
  const target = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1));
  for (let i = 0; i < 60; i++) {
    const id = target.toISOString().slice(0, 7);
    if (!existing.has(id)) return new Date(target); // return copy
    target.setUTCMonth(target.getUTCMonth() - 1);
  }
  return null;
}

interface Env {
  SUPABASE_URL: string;
  SUPABASE_KEY: string;
  HISTORY_BUCKET: R2Bucket;
}

export default {
  async fetch(_req: Request): Promise<Response> {
    return new Response('This worker only runs on schedule');
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_KEY);

    const list = await env.HISTORY_BUCKET.list();
    const keys = list.objects.map(o => o.key);
    const target = getNextMonthToArchive(keys, new Date());

    if (!target) {
      console.log('No months left to archive');
      return;
    }

    const year = target.getUTCFullYear();
    const month = target.getUTCMonth();

    const startTs = Math.floor(Date.UTC(year, month, 1) / 1000);
    const endTs = Math.floor(Date.UTC(year, month + 1, 0, 23, 59, 59, 999) / 1000);

    const { data, error } = await supabase
      .from('locations')
      .select('lat,lon,acc,alt,vel,batt,ssid,tag,topic,tid,tst,conn')
      .gte('tst', startTs)
      .lte('tst', endTs)
      .order('tst', { ascending: true });

    if (error) {
      console.error('Supabase query error', error);
      return;
    }

    const json = JSON.stringify({ type: 'FeatureCollection', features: data });
    const compressed = new Blob([json]).stream().pipeThrough(new CompressionStream('gzip'));
    const key = `${target.toISOString().slice(0, 7)}.json.gz`;
    await env.HISTORY_BUCKET.put(key, compressed, {
      httpMetadata: { contentType: 'application/json' },
    });
    console.log(`Wrote ${data.length} records to ${key}`);
  },
} satisfies ExportedHandler<Env>;
