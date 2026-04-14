import { describe, expect, it } from 'vitest';

import { formatDateTime } from './datetime';

describe('datetime formatting', () => {
  it('formats utc-marked timestamps in the browser local timezone', () => {
    expect(formatDateTime('2026-04-11T08:07:19Z')).toBe(new Date('2026-04-11T08:07:19Z').toLocaleString('zh-CN'));
  });

  it('returns a fallback for empty or invalid values', () => {
    expect(formatDateTime(null)).toBe('-');
    expect(formatDateTime('not-a-date')).toBe('not-a-date');
  });
});
