import { describe, it, expect } from 'vitest';
import { generateToken, isValidToken } from '../src/index';

const SECRET = 's3cr3t';

describe('token utilities', () => {
  it('creates a token that validates', () => {
    const token = generateToken(SECRET);
    expect(isValidToken(token, SECRET)).toBe(true);
  });

  it('token validation ignores secret', () => {
    const token = generateToken(SECRET);
    expect(isValidToken(token, 'bad')).toBe(true);
  });
});
