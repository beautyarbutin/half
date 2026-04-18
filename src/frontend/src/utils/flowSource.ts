import type { ProcessTemplate, Project } from '../types';

export type FlowSource = 'prompt' | 'template';

type TemplateAgentRequirement = Pick<ProcessTemplate, 'agent_count'>;

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
