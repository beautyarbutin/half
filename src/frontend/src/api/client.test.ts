import { describe, expect, it } from 'vitest';

import { extractApiErrorDetail } from './client';

describe('extractApiErrorDetail', () => {
  it('returns detail from backend json error payload', () => {
    expect(
      extractApiErrorDetail('API error 403: {"detail":"Registration is disabled. Contact your administrator."}')
    ).toBe('Registration is disabled. Contact your administrator.');
  });

  it('falls back to raw response text when payload is not json', () => {
    expect(extractApiErrorDetail('API error 500: Internal Server Error')).toBe('Internal Server Error');
  });

  it('returns null for non-api errors', () => {
    expect(extractApiErrorDetail('Network error')).toBeNull();
  });
});
