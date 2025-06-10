import { describe, it, expect } from 'vitest';
import { calculateDistance } from '../src/index';

describe('distance calculation', () => {
  it('returns ~0 for same coordinates', () => {
    expect(calculateDistance(0, 0, 0, 0)).toBeCloseTo(0);
  });

  it('computes known distance', () => {
    // distance between New York (40.7128,-74.0060) and London (51.5074,-0.1278)
    const d = calculateDistance(40.7128, -74.0060, 51.5074, -0.1278);
    expect(d).toBeGreaterThan(5500000);
    expect(d).toBeLessThan(5600000);
  });
});
