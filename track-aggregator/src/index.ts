import { createClient } from '@supabase/supabase-js';

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

    const yesterday = new Date();
    yesterday.setUTCDate(yesterday.getUTCDate() - 1);
    const day = yesterday.toISOString().slice(0, 10); // YYYY-MM-DD
    const startTs = Math.floor(yesterday.setUTCHours(0, 0, 0, 0) / 1000);
    const endTs = Math.floor(yesterday.setUTCHours(23, 59, 59, 999) / 1000);

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
    const key = `${day}.json.gz`;
    await env.HISTORY_BUCKET.put(key, compressed, {
      httpMetadata: { contentType: 'application/json' },
    });
    console.log(`Wrote ${data.length} records to ${key}`);
  },
} satisfies ExportedHandler<Env>;
