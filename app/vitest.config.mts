import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
        resolve: {
                alias: {
                        '@supabase/node-fetch': '/workspace/NerdTracker/test/node-fetch.ts',
                        '@supabase/supabase-js': '/workspace/NerdTracker/test/supabase.ts'
                }
        },
        test: {
                poolOptions: {
                        workers: {
                                wrangler: { configPath: './wrangler.toml' },
                        },
                },
        },
});
