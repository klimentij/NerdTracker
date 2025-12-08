/**
 * @vitest-environment node
 */

import { beforeAll, afterAll, beforeEach, afterEach, test, expect } from 'vitest';
import { GenericContainer, StartedTestContainer } from 'testcontainers';
import { Client } from 'pg';
import fs from 'fs/promises';
import path from 'path';

let container: StartedTestContainer;
let client: Client;

beforeAll(async () => {
	// Start a fresh PostgreSQL container
	container = await new GenericContainer('postgres')
		.withEnvironment({
			'POSTGRES_PASSWORD': 'postgres',
			'POSTGRES_DB': 'test',
		})
		.withExposedPorts(5432)
		.start();

	// Wait for DB to be ready and connect
	client = new Client({
		user: 'postgres',
		host: container.getHost(),
		database: 'test',
		password: 'postgres',
		port: container.getMappedPort(5432),
	});
	await client.connect();

	// Run schema and function setup
	// Adjust the path to your SQL file as needed
	const dbpath: string = '../../db';
	const sqlFiles = await fs.readdir(path.resolve(__dirname, dbpath));
	for (const file of sqlFiles) {
		if (file.endsWith('.sql')) {
			const sql = await fs.readFile(path.resolve(__dirname, dbpath, file), 'utf-8');
			await client.query(sql);
		}
	}
});

afterAll(async () => {
	await client.end();
	await container.stop({ remove: true });
});

beforeEach(async () => {
	await client.query('BEGIN');
});

afterEach(async () => {
	await client.query('ROLLBACK');
});

class Generator {
    static id: number = 0;

    static get() {
		return ++this.id;
    }

	static last() {
		return this.id;
    }
}

const testCases = [
	{
		name: 'if 5 points are closer 100m, only update the last record',
		before: async () => {
			for (let i = 0; i < 5; i++) {
				await client.query("INSERT INTO locations_no_dups(lat, lon, tid, tst) VALUES (55.0000, 37.0000, 'AB', $1)", [Generator.get()]);
			}
		},
		insert: async () => {
			await client.query("INSERT INTO locations_no_dups(lat, lon, tid, tst) VALUES (55.0000, 37.0000, 'AB', $1)", [Generator.get()]); // the same is ignored
			await client.query("INSERT INTO locations_no_dups(lat, lon, tid, tst) VALUES (55.0001, 37.0001, 'AB', $1)", [Generator.get()]); // ~13m
		},
		compare: async (oldRows: any[], newRows: any[]) => {
			expect(oldRows.length).toBe(5);
			expect(newRows.length).toBe(5);
			expect(newRows[newRows.length - 1]['lat']).toBe(55.0001);
			expect(newRows[newRows.length - 1]['lon']).toBe(37.0001);
			expect(Number(newRows[newRows.length - 1]['tst'])).toBe(Generator.last());
		}
	},
	{
		name: 'different person should have 5 points each',
		before: async () => {
			for (let i = 0; i < 5; i++) {
				await client.query("INSERT INTO locations_no_dups(lat, lon, tid, tst) VALUES (55.0000, 37.0000, 'AB', $1)", [Generator.get()]);
				await client.query("INSERT INTO locations_no_dups(lat, lon, tid, tst) VALUES (55.0000, 37.0000, 'BC', $1)", [Generator.get()]);
			}
		},
		insert: async () => {
			await client.query("INSERT INTO locations_no_dups(lat, lon, tid, tst) VALUES (55.0000, 37.0000, 'AB', $1)", [Generator.get()]); // the same is ignored
			await client.query("INSERT INTO locations_no_dups(lat, lon, tid, tst) VALUES (55.0001, 37.0001, 'BC', $1)", [Generator.get()]); // ~13m
		},
		compare: async (oldRows: any[], newRows: any[]) => {
			expect(oldRows.length).toBe(10);
			expect(newRows.length).toBe(10);
			expect(newRows[newRows.length - 1]['lat']).toBe(55.0001);
			expect(newRows[newRows.length - 1]['lon']).toBe(37.0001);
			expect(Number(newRows[newRows.length - 1]['tst'])).toBe(Generator.last());
		}
	},
];

testCases.forEach(({ name, before, insert, compare }) => {
	test(name, async () => {
		await before();
		const oldRows = (await client.query("SELECT * FROM locations ORDER BY id")).rows;
		await insert();
		const newRows = (await client.query("SELECT * FROM locations ORDER BY id")).rows;
		await compare(oldRows, newRows);
	});
});
