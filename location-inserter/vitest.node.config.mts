import { defineConfig } from 'vitest/config'

export default defineConfig({
    test: {
        environment: 'node',
        isolate: false,
		pool: 'forks',
        include: ['test/db.test.ts'],
    },
})
