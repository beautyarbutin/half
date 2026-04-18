import { describe, expect, it } from 'vitest';
import {
  buildRolesPayload,
  getTemplateAgentSlots,
  parseAgentRolesFromTemplateJson,
  syncRolesForSlots,
} from './processTemplateRoles';

function templateJson(overrides: Record<string, unknown> = {}) {
  return JSON.stringify({
    agent_roles: [],
    tasks: [
      { task_code: 'T1', assignee: 'agent-2' },
      { task_code: 'T2', assignee: 'agent-1' },
      { task_code: 'T3', assignee: 'agent-3' },
    ],
    ...overrides,
  });
}

describe('process template role helpers', () => {
  it('extracts dynamic agent slots from tasks and sorts by slot number', () => {
    expect(getTemplateAgentSlots(templateJson())).toEqual(['agent-1', 'agent-2', 'agent-3']);
  });

  it('ignores invalid agent role descriptions and keeps the first description per slot', () => {
    const json = templateJson({
      agent_roles: [
        { slot: 'agent-1', description: '  初审角色  ' },
        { slot: 'agent-1', description: '重复说明不应覆盖' },
        { slot: 'agent-2', description: '   ' },
        { slot: 'agent-3', description: 123 },
        { slot: 'agent-9', description: '无效 slot' },
      ],
    });

    expect(parseAgentRolesFromTemplateJson(json, ['agent-1', 'agent-2', 'agent-3'])).toEqual({
      'agent-1': '初审角色',
    });
  });

  it('prefills empty slots without overwriting manually edited descriptions', () => {
    expect(syncRolesForSlots(
      { 'agent-1': '手工说明', 'agent-2': '' },
      ['agent-1', 'agent-2'],
      { 'agent-1': 'AI 新说明', 'agent-2': 'AI 复审说明' },
    )).toEqual({
      'agent-1': '手工说明',
      'agent-2': 'AI 复审说明',
    });
  });

  it('drops removed slots and adds newly parsed slots', () => {
    expect(syncRolesForSlots(
      { 'agent-1': '保留', 'agent-2': '丢弃' },
      ['agent-1', 'agent-3'],
      { 'agent-3': '新增' },
    )).toEqual({
      'agent-1': '保留',
      'agent-3': '新增',
    });
  });

  it('builds a trimmed payload only for current non-empty slots', () => {
    expect(buildRolesPayload(
      { 'agent-1': '  初审  ', 'agent-2': '', 'agent-4': '孤儿说明' },
      ['agent-1', 'agent-2', 'agent-3'],
    )).toEqual({
      'agent-1': '初审',
    });
  });
});
