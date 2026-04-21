import { describe, expect, it } from 'vitest';

import { extractApiErrorDetail, extractApiErrorPayload } from './client';

describe('extractApiErrorDetail', () => {
  it('returns detail from backend json error payload', () => {
    expect(
      extractApiErrorDetail('API error 403: {"detail":"Registration is disabled. Contact your administrator."}')
    ).toBe('Registration is disabled. Contact your administrator.');
  });

  it('falls back to raw response text when payload is not json', () => {
    expect(extractApiErrorDetail('API error 500: Internal Server Error')).toBe('Internal Server Error');
  });

  it('parses api errors wrapped by Error.toString()', () => {
    expect(
      extractApiErrorDetail('Error: API error 400: {"detail":"当前密码错误"}')
    ).toBe('当前密码错误');
  });

  it('extracts nested unavailable agent ids from backend payloads', () => {
    expect(
      extractApiErrorPayload(
        'API error 400: {"detail":{"message":"Some selected agents are unavailable","unavailable_agent_ids":[2,3]}}'
      )
    ).toEqual({
      detail: 'Some selected agents are unavailable',
      unavailableAgentIds: [2, 3],
    });
  });

  it('returns null for non-api errors', () => {
    expect(extractApiErrorDetail('Network error')).toBeNull();
  });
});
