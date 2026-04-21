export type AgentRolesDescription = Record<string, string>;

const AGENT_SLOT_PATTERN = /^agent-[1-9]\d*$/;

function slotSortKey(slot: string): [number, string] {
  const match = /^agent-(\d+)$/.exec(slot);
  return [match ? Number(match[1]) : Number.MAX_SAFE_INTEGER, slot];
}

export function getTemplateAgentSlots(templateJson: string): string[] {
  const parsed = JSON.parse(templateJson);
  const tasks = Array.isArray(parsed.tasks) ? parsed.tasks : [];
  const slots = new Set<string>();
  tasks.forEach((task: Record<string, unknown>) => {
    const assignee = String(task.assignee || '').trim();
    if (AGENT_SLOT_PATTERN.test(assignee)) {
      slots.add(assignee);
    }
  });
  return Array.from(slots).sort((left, right) => {
    const [leftNumber, leftText] = slotSortKey(left);
    const [rightNumber, rightText] = slotSortKey(right);
    return leftNumber - rightNumber || leftText.localeCompare(rightText);
  });
}

export function parseAgentRolesFromTemplateJson(templateJson: string, slots: string[]): AgentRolesDescription {
  const parsed = JSON.parse(templateJson);
  const roles = Array.isArray(parsed.agent_roles) ? parsed.agent_roles : [];
  const slotSet = new Set(slots);
  const descriptions: AgentRolesDescription = {};
  roles.forEach((role: unknown) => {
    if (!role || typeof role !== 'object') return;
    const item = role as Record<string, unknown>;
    const slot = String(item.slot || '').trim();
    const description = typeof item.description === 'string' ? item.description.trim() : '';
    if (slotSet.has(slot) && description && !descriptions[slot]) {
      descriptions[slot] = description;
    }
  });
  return descriptions;
}

export function syncRolesForSlots(
  current: AgentRolesDescription,
  slots: string[],
  prefill: AgentRolesDescription = {},
): AgentRolesDescription {
  const next: AgentRolesDescription = {};
  slots.forEach((slot) => {
    const currentValue = current[slot] || '';
    const prefillValue = prefill[slot] || '';
    next[slot] = currentValue.trim() ? currentValue : prefillValue;
  });
  return next;
}

export function syncRolesForPreview(
  current: AgentRolesDescription,
  slots: string[],
  prefill: AgentRolesDescription = {},
  previousPrefill: AgentRolesDescription = {},
  touched: Record<string, boolean> = {},
): AgentRolesDescription {
  const next: AgentRolesDescription = {};
  slots.forEach((slot) => {
    const currentValue = current[slot] || '';
    const prefillValue = prefill[slot] || '';
    const previousPrefillValue = previousPrefill[slot] || '';

    if (touched[slot]) {
      next[slot] = currentValue;
      return;
    }

    if (!currentValue.trim()) {
      next[slot] = prefillValue;
      return;
    }

    if (previousPrefillValue && currentValue === previousPrefillValue) {
      next[slot] = prefillValue || currentValue;
      return;
    }

    next[slot] = currentValue;
  });
  return next;
}

export function buildRolesPayload(roles: AgentRolesDescription, slots: string[]): AgentRolesDescription {
  const payload: AgentRolesDescription = {};
  slots.forEach((slot) => {
    const description = roles[slot]?.trim();
    if (description) {
      payload[slot] = description;
    }
  });
  return payload;
}
