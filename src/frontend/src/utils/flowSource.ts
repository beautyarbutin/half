import type { ProcessTemplate, Project } from '../types';

export type FlowSource = 'prompt' | 'template';

type TemplateAgentRequirement = Pick<ProcessTemplate, 'agent_count'>;
export const PLAN_SOURCE_PREF_KEY_PREFIX = 'plan_source_pref';

export function isFlowSource(value: string | null): value is FlowSource {
  return value === 'prompt' || value === 'template';
}

export function buildPlanSourcePrefKey(ownerUserId: number, projectId: string | number): string {
  return `${PLAN_SOURCE_PREF_KEY_PREFIX}:${ownerUserId}:${projectId}`;
}

export function hasUsableProcessTemplate(
  projectAgentIds: Project['agent_ids'],
  templates: TemplateAgentRequirement[],
): boolean {
  const projectAgentCount = projectAgentIds?.length ?? 0;
  return templates.some((template) => projectAgentCount >= template.agent_count);
}

export function getInitialFlowSource(
  projectAgentIds: Project['agent_ids'],
  templates: TemplateAgentRequirement[],
): FlowSource {
  return hasUsableProcessTemplate(projectAgentIds, templates) ? 'template' : 'prompt';
}

export function resolveFlowSourcePreference(
  storedValue: string | null,
  projectAgentIds: Project['agent_ids'],
  templates: TemplateAgentRequirement[],
): FlowSource {
  const defaultSource = getInitialFlowSource(projectAgentIds, templates);
  if (!isFlowSource(storedValue)) {
    return defaultSource;
  }
  if (storedValue === 'template' && defaultSource === 'prompt') {
    return defaultSource;
  }
  return storedValue;
}
