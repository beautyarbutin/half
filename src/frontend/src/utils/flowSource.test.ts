import { describe, expect, it } from 'vitest';

import {
  buildPlanSourcePrefKey,
  getInitialFlowSource,
  hasUsableProcessTemplate,
  isFlowSource,
  resolveFlowSourcePreference,
} from './flowSource';

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

  it('builds project and user scoped local storage keys', () => {
    expect(buildPlanSourcePrefKey(7, 42)).toBe('plan_source_pref:7:42');
  });

  it('validates stored flow source values', () => {
    expect(isFlowSource('prompt')).toBe(true);
    expect(isFlowSource('template')).toBe(true);
    expect(isFlowSource('bad-value')).toBe(false);
    expect(isFlowSource(null)).toBe(false);
  });

  it('uses a valid stored prompt preference over the default template source', () => {
    expect(resolveFlowSourcePreference('prompt', [1, 2], [{ agent_count: 2 }])).toBe('prompt');
  });

  it('falls back to the computed default when the stored preference is invalid', () => {
    expect(resolveFlowSourcePreference('bad-value', [1, 2], [{ agent_count: 2 }])).toBe('template');
    expect(resolveFlowSourcePreference(null, [1, 2], [])).toBe('prompt');
  });

  it('does not restore template preference when no template is usable', () => {
    expect(resolveFlowSourcePreference('template', [1], [{ agent_count: 2 }])).toBe('prompt');
  });
});
