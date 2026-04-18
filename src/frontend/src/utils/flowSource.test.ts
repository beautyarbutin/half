import { describe, expect, it } from 'vitest';

import { getInitialFlowSource, hasUsableProcessTemplate } from './flowSource';

describe('flow source defaults', () => {
  it('keeps the template path when at least one template fits the project agent count', () => {
    expect(getInitialFlowSource([1, 2], [
      { agent_count: 3 },
      { agent_count: 2 },
    ])).toBe('template');
  });

  it('falls back to prompt when there are no templates', () => {
    expect(getInitialFlowSource([1, 2], [])).toBe('prompt');
  });

  it('falls back to prompt when every template needs more agents than the project has', () => {
    expect(getInitialFlowSource([1], [
      { agent_count: 2 },
      { agent_count: 3 },
    ])).toBe('prompt');
  });

  it('treats missing project agent ids as zero usable agents', () => {
    expect(hasUsableProcessTemplate(undefined, [{ agent_count: 1 }])).toBe(false);
    expect(getInitialFlowSource(undefined, [{ agent_count: 1 }])).toBe('prompt');
  });

  it('does not require loaded Agent objects to decide template usability', () => {
    expect(hasUsableProcessTemplate([101, 102, 103], [{ agent_count: 3 }])).toBe(true);
  });
});
