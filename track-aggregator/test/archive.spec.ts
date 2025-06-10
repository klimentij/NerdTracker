import { describe, it, expect } from 'vitest';
import { getNextMonthToArchive } from '../src/index';

const base = new Date(Date.UTC(2025, 5, 15)); // June 2025

describe('getNextMonthToArchive', () => {
  it('returns previous month when none exist', () => {
    const next = getNextMonthToArchive([], base);
    expect(next?.toISOString().slice(0,7)).toBe('2025-05');
  });

  it('skips existing months', () => {
    const next = getNextMonthToArchive(['2025-05.json.gz'], base);
    expect(next?.toISOString().slice(0,7)).toBe('2025-04');
  });
});
