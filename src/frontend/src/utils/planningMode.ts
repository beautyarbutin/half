export type PlanningMode = 'balanced' | 'quality' | 'cost_effective' | 'speed';

export const DEFAULT_PLANNING_MODE: PlanningMode = 'balanced';

export const PLANNING_MODE_OPTIONS: Array<{ value: PlanningMode; label: string; description: string }> = [
  {
    value: 'balanced',
    label: '均衡模式',
    description: '以良好效果为主要目标，每个 task 安排效果最好的 agent。',
  },
  {
    value: 'quality',
    label: '效果优先',
    description: '只考虑效果，允许多 agent 同 task 优选、agent 互评等，不考虑成本和速度。',
  },
  {
    value: 'cost_effective',
    label: '性价比高',
    description: '确保效果较理想前提下，优先用成本较低的模型。',
  },
  {
    value: 'speed',
    label: '速度优先',
    description: '确保效果理想前提下，提升并发度缩短完成时间。',
  },
];

export function normalizePlanningMode(value?: string | null): PlanningMode {
  return PLANNING_MODE_OPTIONS.some((option) => option.value === value)
    ? (value as PlanningMode)
    : DEFAULT_PLANNING_MODE;
}

export function getPlanningModeMeta(value?: string | null) {
  const normalized = normalizePlanningMode(value);
  return PLANNING_MODE_OPTIONS.find((option) => option.value === normalized) || PLANNING_MODE_OPTIONS[0];
}
