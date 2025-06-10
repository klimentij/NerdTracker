import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      '@supabase/supabase-js': '/workspace/NerdTracker/test/supabase.ts',
      '@supabase/node-fetch': '/workspace/NerdTracker/test/node-fetch.ts'
    }
  }
});
