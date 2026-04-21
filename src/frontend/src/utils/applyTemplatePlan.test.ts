import { describe, expect, it, vi } from 'vitest';

import { applyTemplatePlan, filterTemplateInputs, getMissingTemplateInputs } from './applyTemplatePlan';
import type { TemplateApplyApi } from './applyTemplatePlan';

function createApi(): TemplateApplyApi {
  return {
    put: vi.fn(async () => ({})),
    post: vi.fn(async () => ({})),
  };
}

describe('applyTemplatePlan', () => {
  it('filters template inputs to declared keys and detects missing required values', () => {
    const requiredInputs = [
      { key: 'test_url', label: '测试系统 URL', required: true, sensitive: false },
      { key: 'password', label: '密码', required: true, sensitive: true },
      { key: 'report_path', label: '报告输出路径', required: false, sensitive: false },
    ];

    expect(filterTemplateInputs(requiredInputs, {
      test_url: 'https://example.test',
      password: ' secret ',
      extra: 'ignored',
    })).toEqual({
      test_url: 'https://example.test',
      password: ' secret ',
      report_path: '',
    });
    expect(getMissingTemplateInputs(requiredInputs, { test_url: 'https://example.test', password: '   ' }))
      .toEqual([requiredInputs[1]]);
  });

  it('rejects an empty planning brief before any request', async () => {
    const api = createApi();

    await expect(applyTemplatePlan({
      api,
      projectId: 12,
      templateId: 3,
      planningBrief: '   ',
      slotAgentIds: { 'agent-1': 1 },
      templateMappingComplete: true,
    })).rejects.toThrow('请先填写任务介绍。');

    expect(api.put).not.toHaveBeenCalled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('rejects missing required template inputs before any request', async () => {
    const api = createApi();

    await expect(applyTemplatePlan({
      api,
      projectId: 12,
      templateId: 3,
      planningBrief: '完成系统测试',
      slotAgentIds: { 'agent-1': 1 },
      templateMappingComplete: true,
      requiredInputs: [
        { key: 'test_url', label: '测试系统 URL', required: true, sensitive: false },
      ],
      templateInputs: { test_url: '   ' },
    })).rejects.toThrow('请填写所有模版所需信息。');

    expect(api.put).not.toHaveBeenCalled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('saves goal before applying the selected template', async () => {
    const calls: string[] = [];
    const api: TemplateApplyApi = {
      put: vi.fn(async () => {
        calls.push('put');
        return {};
      }),
      post: vi.fn(async () => {
        calls.push('post');
        return {};
      }),
    };

    await applyTemplatePlan({
      api,
      projectId: 12,
      templateId: 3,
      planningBrief: '完成支付回调改造',
      slotAgentIds: { 'agent-1': 1, 'agent-2': 2 },
      templateMappingComplete: true,
      requiredInputs: [
        { key: 'test_url', label: '测试系统 URL', required: true, sensitive: false },
        { key: 'login_password', label: '登录密码', required: true, sensitive: true },
      ],
      templateInputs: {
        test_url: 'https://example.test',
        login_password: 'secret',
        extra: 'ignored',
      },
    });

    expect(calls).toEqual(['put', 'post']);
    expect(api.put).toHaveBeenCalledWith('/api/projects/12', {
      goal: '完成支付回调改造',
      template_inputs: {
        test_url: 'https://example.test',
        login_password: 'secret',
      },
    });
    expect(api.post).toHaveBeenCalledWith('/api/process-templates/3/apply/12', {
      slot_agent_ids: { 'agent-1': 1, 'agent-2': 2 },
    });
  });

  it('does not apply the template when saving goal fails', async () => {
    const api: TemplateApplyApi = {
      put: vi.fn(async () => {
        throw new Error('save failed');
      }),
      post: vi.fn(async () => ({})),
    };

    await expect(applyTemplatePlan({
      api,
      projectId: 12,
      templateId: 3,
      planningBrief: '完成支付回调改造',
      slotAgentIds: { 'agent-1': 1 },
      templateMappingComplete: true,
    })).rejects.toThrow('save failed');

    expect(api.post).not.toHaveBeenCalled();
  });
});
