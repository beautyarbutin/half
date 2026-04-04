import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { api } from '../api/client';
import { Agent } from '../types';
import StatusBadge from '../components/StatusBadge';

interface AgentForm {
  name: string;
  agent_type: string;
  custom_agent_type: string;
  model_name: string;
  custom_model_name: string;
  machine_label: string;
  capability: string;
  subscription_expires_at: string;
  short_term_reset_at: string;
  short_term_reset_timezone: string;
  short_term_reset_interval_hours: string;
  long_term_reset_at: string;
  long_term_reset_timezone: string;
  long_term_reset_interval_days: string;
}

const AGENT_TYPE_OPTIONS = ['claude', 'codex', 'cursor', 'windsurf'];
const MODEL_OPTIONS: Record<string, string[]> = {
  claude: ['claude-sonnet-4-5', 'claude-opus-4-1', 'claude-3-7-sonnet-latest'],
  codex: ['codex-mini-latest', 'codex-1', 'gpt-5-codex'],
  cursor: ['cursor-default', 'gpt-5', 'claude-sonnet-4-5'],
  windsurf: ['windsurf-default', 'claude-sonnet-4-5', 'gpt-5'],
};

const emptyForm: AgentForm = {
  name: '',
  agent_type: '',
  custom_agent_type: '',
  model_name: '',
  custom_model_name: '',
  machine_label: '',
  capability: '',
  subscription_expires_at: '',
  short_term_reset_at: '',
  short_term_reset_timezone: 'CST',
  short_term_reset_interval_hours: '',
  long_term_reset_at: '',
  long_term_reset_timezone: 'CST',
  long_term_reset_interval_days: '',
};

const TIMEZONE_OPTIONS = [
  { value: 'CST', label: 'CST (UTC+8，北京时间)', offsetMinutes: 8 * 60 },
  { value: 'UTC', label: 'UTC (UTC+0)', offsetMinutes: 0 },
  { value: 'GMT', label: 'GMT (UTC+0)', offsetMinutes: 0 },
  { value: 'EST', label: 'EST (UTC-5)', offsetMinutes: -5 * 60 },
  { value: 'EDT', label: 'EDT (UTC-4)', offsetMinutes: -4 * 60 },
  { value: 'CET', label: 'CET (UTC+1)', offsetMinutes: 60 },
  { value: 'CEST', label: 'CEST (UTC+2)', offsetMinutes: 120 },
  { value: 'PST', label: 'PST (UTC-8)', offsetMinutes: -8 * 60 },
  { value: 'PDT', label: 'PDT (UTC-7)', offsetMinutes: -7 * 60 },
];

function pad2(value: number) {
  return String(value).padStart(2, '0');
}

function formatForDateTimeLocal(value: string | null | undefined) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function parseDateTimeLocal(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  return {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
  };
}

function parseStoredDateTime(value: string | null | undefined) {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(value);
  if (!match) return null;
  return {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
  };
}

function formatPartsForDateTimeLocal(parts: ReturnType<typeof parseDateTimeLocal>) {
  if (!parts) return '';
  return `${parts.year}-${pad2(parts.month)}-${pad2(parts.day)}T${pad2(parts.hour)}:${pad2(parts.minute)}`;
}

function formatPartsForDisplay(parts: ReturnType<typeof parseDateTimeLocal>) {
  if (!parts) return <span className="text-muted">-</span>;
  return `${parts.year}/${parts.month}/${parts.day} ${pad2(parts.hour)}:${pad2(parts.minute)}`;
}

function formatPartsForPreview(parts: ReturnType<typeof parseDateTimeLocal>) {
  if (!parts) return '未设置';
  return `${parts.year}/${parts.month}/${parts.day} ${pad2(parts.hour)}:${pad2(parts.minute)}`;
}

function convertToBeijingLocalValue(localValue: string, timezoneCode: string) {
  if (!localValue) return null;
  const parsed = parseDateTimeLocal(localValue);
  if (!parsed) return null;
  const timezone = TIMEZONE_OPTIONS.find((option) => option.value === timezoneCode) || TIMEZONE_OPTIONS[0];
  const totalMinutes = (parsed.hour * 60 + parsed.minute) - timezone.offsetMinutes + (8 * 60);
  const shiftedDate = new Date(Date.UTC(parsed.year, parsed.month - 1, parsed.day, 0, 0));
  shiftedDate.setUTCMinutes(totalMinutes);
  return [
    shiftedDate.getUTCFullYear(),
    pad2(shiftedDate.getUTCMonth() + 1),
    pad2(shiftedDate.getUTCDate()),
  ].join('-') + `T${pad2(shiftedDate.getUTCHours())}:${pad2(shiftedDate.getUTCMinutes())}`;
}

function formatBeijingPreview(localValue: string, timezoneCode: string) {
  return formatPartsForPreview(parseStoredDateTime(convertToBeijingLocalValue(localValue, timezoneCode)));
}

function formatBeijingStoredForInput(value: string | null | undefined) {
  return formatPartsForDateTimeLocal(parseStoredDateTime(value));
}

function formatBeijingTime(value: string | null | undefined) {
  return formatPartsForDisplay(parseStoredDateTime(value));
}

function beijingPartsToEpoch(parts: ReturnType<typeof parseDateTimeLocal>) {
  if (!parts) return Number.NaN;
  return Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour - 8, parts.minute);
}

function getCurrentBeijingParts() {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const values = Object.fromEntries(
    formatter.formatToParts(new Date())
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, Number(part.value)]),
  );
  return {
    year: values.year,
    month: values.month,
    day: values.day,
    hour: values.hour,
    minute: values.minute,
  };
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<AgentForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [actionAgentId, setActionAgentId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [nowTick, setNowTick] = useState(() => Date.now());

  const effectiveAgentType = form.agent_type === '__custom__' ? form.custom_agent_type.trim() : form.agent_type;
  const modelOptions = useMemo(() => MODEL_OPTIONS[effectiveAgentType] || [], [effectiveAgentType]);
  const usesCustomModel = form.model_name === '__custom__' || (form.model_name === '' && modelOptions.length === 0 && !!form.custom_model_name);

  const fetchAgents = useCallback(() => {
    api.get<Agent[]>('/api/agents')
      .then(setAgents)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  useEffect(() => {
    const countdownTimer = window.setInterval(() => {
      setNowTick(Date.now());
    }, 30 * 1000);
    const refreshTimer = window.setInterval(() => {
      fetchAgents();
    }, 60 * 1000);
    return () => {
      window.clearInterval(countdownTimer);
      window.clearInterval(refreshTimer);
    };
  }, [fetchAgents]);

  function handleAdd() {
    setForm(emptyForm);
    setEditingId(null);
    setShowForm(true);
    setError('');
  }

  function handleEdit(agent: Agent) {
    const knownType = AGENT_TYPE_OPTIONS.includes(agent.agent_type);
    const knownModels = MODEL_OPTIONS[agent.agent_type] || [];
    const knownModel = agent.model_name ? knownModels.includes(agent.model_name) : false;
    setForm({
      name: agent.name,
      agent_type: knownType ? agent.agent_type : '__custom__',
      custom_agent_type: knownType ? '' : agent.agent_type,
      model_name: agent.model_name ? (knownModel ? agent.model_name : '__custom__') : '',
      custom_model_name: agent.model_name && !knownModel ? agent.model_name : '',
      machine_label: agent.machine_label || '',
      capability: agent.capability || '',
      subscription_expires_at: formatForDateTimeLocal(agent.subscription_expires_at),
      short_term_reset_at: formatBeijingStoredForInput(agent.short_term_reset_at),
      short_term_reset_timezone: 'CST',
      short_term_reset_interval_hours: agent.short_term_reset_interval_hours != null ? String(agent.short_term_reset_interval_hours) : '',
      long_term_reset_at: formatBeijingStoredForInput(agent.long_term_reset_at),
      long_term_reset_timezone: 'CST',
      long_term_reset_interval_days: agent.long_term_reset_interval_days != null ? String(agent.long_term_reset_interval_days) : '',
    });
    setEditingId(agent.id);
    setShowForm(true);
    setError('');
  }

  function handleCancel() {
    setShowForm(false);
    setEditingId(null);
    setError('');
  }

  function updateField(field: keyof AgentForm, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');

    const resolvedAgentType = effectiveAgentType;
    const resolvedModelName = form.model_name === '__custom__' ? form.custom_model_name.trim() : form.model_name.trim();

    try {
      const payload = {
        name: form.name.trim(),
        agent_type: resolvedAgentType,
        model_name: resolvedModelName || null,
        capability: form.capability.trim() || null,
        subscription_expires_at: form.subscription_expires_at || null,
        short_term_reset_at: convertToBeijingLocalValue(form.short_term_reset_at, form.short_term_reset_timezone),
        short_term_reset_interval_hours: form.short_term_reset_interval_hours.trim() ? Number(form.short_term_reset_interval_hours) : null,
        long_term_reset_at: convertToBeijingLocalValue(form.long_term_reset_at, form.long_term_reset_timezone),
        long_term_reset_interval_days: form.long_term_reset_interval_days.trim() ? Number(form.long_term_reset_interval_days) : null,
      };
      if (editingId) {
        await api.put(`/api/agents/${editingId}`, payload);
      } else {
        await api.post('/api/agents', payload);
      }
      setShowForm(false);
      setEditingId(null);
      fetchAgents();
    } catch (err) {
      setError(`保存 Agent 失败：${err}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(agent: Agent) {
    if (!confirm(`确认删除 Agent “${agent.name}” 吗？`)) return;
    setDeletingId(agent.id);
    setError('');
    try {
      await api.delete(`/api/agents/${agent.id}`);
      fetchAgents();
    } catch (err) {
      setError(`删除 Agent 失败：${err}`);
    } finally {
      setDeletingId(null);
    }
  }

  async function handleResetAction(agentId: number, mode: 'short' | 'long') {
    setActionAgentId(agentId);
    setError('');
    try {
      const updatedAgent = await api.post<Agent>(`/api/agents/${agentId}/${mode === 'short' ? 'short-term-reset' : 'long-term-reset'}/reset`);
      setAgents((prev) => prev.map((agent) => agent.id === agentId ? updatedAgent : agent));
    } catch (err) {
      setError(`${mode === 'short' ? '短期' : '长期'}重置失败：${err}`);
    } finally {
      setActionAgentId(null);
    }
  }

  async function handleConfirmAction(agentId: number, mode: 'short' | 'long') {
    setActionAgentId(agentId);
    setError('');
    try {
      const updatedAgent = await api.post<Agent>(`/api/agents/${agentId}/${mode === 'short' ? 'short-term-reset' : 'long-term-reset'}/confirm`);
      setAgents((prev) => prev.map((agent) => agent.id === agentId ? updatedAgent : agent));
    } catch (err) {
      setError(`${mode === 'short' ? '短期' : '长期'}确认失败：${err}`);
    } finally {
      setActionAgentId(null);
    }
  }

  // 根据订阅到期时间自动推导可用状态
  function deriveAvailabilityStatus(agent: Agent): string {
    if (agent.subscription_expires_at) {
      const expiresDate = new Date(agent.subscription_expires_at);
      if (!Number.isNaN(expiresDate.getTime()) && expiresDate.getTime() > Date.now()) {
        return 'online';
      }
      return 'expired';
    }
    return agent.availability_status || 'unknown';
  }

  // 计算倒计时
  function formatCountdown(resetTime: string | null | undefined) {
    if (!resetTime) return { display: '-', tooltip: '', diffMs: Infinity };

    const parts = parseStoredDateTime(resetTime);
    const resetEpoch = beijingPartsToEpoch(parts);
    const nowEpoch = beijingPartsToEpoch(getCurrentBeijingParts());
    if (Number.isNaN(resetEpoch) || Number.isNaN(nowEpoch)) return { display: '-', tooltip: '', diffMs: Infinity };
    const diffMs = resetEpoch - nowEpoch;
    const tooltip = parts ? `${parts.year}/${parts.month}/${parts.day} ${pad2(parts.hour)}:${pad2(parts.minute)}` : '';

    if (diffMs < 0) return { display: '已过期', tooltip, diffMs };

    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    const days = Math.floor(diffMinutes / (24 * 60));
    const hours = Math.floor((diffMinutes % (24 * 60)) / 60);
    const minutes = diffMinutes % 60;

    let display = '';
    if (days > 0) {
      display = `${days}d${hours}h${minutes}m`;
    } else if (hours > 0) {
      display = `${hours}h${minutes}m`;
    } else {
      display = `${minutes}m`;
    }

    return { display, tooltip, diffMs };
  }

  // 排序：按最近重置时间排序（最先重置的排最前面）
  const sortedAgents = useMemo(() => {
    return [...agents].sort((a, b) => {
      const getMinResetMs = (agent: Agent) => {
        const times: number[] = [];
        if (agent.short_term_reset_at) {
          const ms = beijingPartsToEpoch(parseStoredDateTime(agent.short_term_reset_at)) - beijingPartsToEpoch(getCurrentBeijingParts());
          if (!Number.isNaN(ms)) times.push(ms);
        }
        if (agent.long_term_reset_at) {
          const ms = beijingPartsToEpoch(parseStoredDateTime(agent.long_term_reset_at)) - beijingPartsToEpoch(getCurrentBeijingParts());
          if (!Number.isNaN(ms)) times.push(ms);
        }
        return times.length > 0 ? Math.min(...times) : Infinity;
      };
      return getMinResetMs(a) - getMinResetMs(b);
    });
  }, [agents, nowTick]);

  if (loading) return <div className="page-loading">正在加载智能体...</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>智能体</h1>
        <button className="btn btn-primary" onClick={handleAdd} title="新增一个可用于项目执行的智能体">
          新增智能体
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {showForm && (
        <div className="agent-form-card">
          <h3>{editingId ? '编辑 Agent' : '新增 Agent'}</h3>
          <form className="form" onSubmit={handleSubmit}>
            <div className="form-row compact-form-row">
              <div className="form-group">
                <label title="填写便于识别的 Agent 名称。">名称</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => updateField('name', e.target.value)}
                  required
                  title="例如：Claude 主力、Codex 执行器。"
                  placeholder="例如：Claude 主力"
                />
              </div>
              <div className="form-group">
                <label title="选择 Agent 类型；如果列表里没有，可切换为自定义。">Agent Type</label>
                <select
                  value={form.agent_type}
                  onChange={(e) => {
                    updateField('agent_type', e.target.value);
                    updateField('model_name', '');
                    updateField('custom_model_name', '');
                  }}
                  title="优先从常见 Agent 类型中选择。"
                >
                  <option value="">请选择 Agent Type</option>
                  {AGENT_TYPE_OPTIONS.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                  <option value="__custom__">其他类型</option>
                </select>
              </div>
            </div>

            {form.agent_type === '__custom__' && (
              <div className="form-group">
                <label title="输入列表里没有的 Agent 类型。">自定义 Agent Type</label>
                <input
                  type="text"
                  value={form.custom_agent_type}
                  onChange={(e) => updateField('custom_agent_type', e.target.value)}
                  required
                  placeholder="例如：custom-runner"
                  title="仅在预设列表没有时填写。"
                />
              </div>
            )}

            <div className="form-group">
              <label title="根据 Agent Type 选择常见模型，没有时可改为手工输入。">Model Name</label>
              {modelOptions.length > 0 ? (
                <select
                  value={form.model_name}
                  onChange={(e) => updateField('model_name', e.target.value)}
                  title="优先选择常见模型。"
                >
                  <option value="">未指定</option>
                  {modelOptions.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                  <option value="__custom__">手工输入</option>
                </select>
              ) : (
                <input
                  type="text"
                  value={form.custom_model_name}
                  onChange={(e) => updateField('custom_model_name', e.target.value)}
                  placeholder="例如：gpt-5-codex"
                  title="当前类型没有预设模型，请手工输入。"
                />
              )}
            </div>

            {modelOptions.length > 0 && form.model_name === '__custom__' && (
              <div className="form-group">
                <label title="输入预设列表中没有的模型名。">自定义 Model Name</label>
                <input
                  type="text"
                  value={form.custom_model_name}
                  onChange={(e) => updateField('custom_model_name', e.target.value)}
                  placeholder="例如：custom-model"
                  title="仅在预设模型没有时填写。"
                />
              </div>
            )}


            <div className="form-group">
              <label title="填写该 Agent 或模型最擅长处理的能力方向，例如长文本分析、任务拆解、代码实现。">能力</label>
              <textarea
                value={form.capability}
                onChange={(e) => updateField('capability', e.target.value)}
                rows={3}
                required
                placeholder="例如：长文本分析、任务拆解、代码实现"
                title="建议用顿号或逗号列出 2 到 5 项核心能力。"
              />
            </div>

            <div className="form-group form-group-half">
              <label title="可选，用于记录 Agent 订阅到期时间。">订阅到期时间</label>
              <input
                type="datetime-local"
                value={form.subscription_expires_at}
                onChange={(e) => updateField('subscription_expires_at', e.target.value)}
                title="选填，填写后会在列表中展示。"
              />
            </div>

            <div className="form-row compact-form-row">
              <div className="form-group">
                <label title="选填，表示下一次短期重置时间。可先按原时区录入，系统会自动换算成北京时间保存。">短期重置</label>
                <input
                  type="datetime-local"
                  value={form.short_term_reset_at}
                  onChange={(e) => updateField('short_term_reset_at', e.target.value)}
                  title="选填，精确到分钟。"
                />
                <select
                  value={form.short_term_reset_timezone}
                  onChange={(e) => updateField('short_term_reset_timezone', e.target.value)}
                  title="选择当前录入时间所属的时区。"
                >
                  {TIMEZONE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <div className="helper-text">北京时间：{formatBeijingPreview(form.short_term_reset_at, form.short_term_reset_timezone)}</div>
              </div>
              <div className="form-group">
                <label title="选填，表示短期重置每隔多少小时自动续推一次。">短期重置间隔（小时）</label>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={form.short_term_reset_interval_hours}
                  onChange={(e) => updateField('short_term_reset_interval_hours', e.target.value)}
                  placeholder="例如：5"
                  title="选填。设置后，短期重置时间到期会自动加上该间隔。"
                />
              </div>
            </div>

            <div className="form-row compact-form-row">
              <div className="form-group">
                <label title="选填，表示下一次长期重置时间。可先按原时区录入，系统会自动换算成北京时间保存。">长期重置</label>
                <input
                  type="datetime-local"
                  value={form.long_term_reset_at}
                  onChange={(e) => updateField('long_term_reset_at', e.target.value)}
                  title="选填，精确到分钟。"
                />
                <select
                  value={form.long_term_reset_timezone}
                  onChange={(e) => updateField('long_term_reset_timezone', e.target.value)}
                  title="选择当前录入时间所属的时区。"
                >
                  {TIMEZONE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <div className="helper-text">北京时间：{formatBeijingPreview(form.long_term_reset_at, form.long_term_reset_timezone)}</div>
              </div>
              <div className="form-group">
                <label title="选填，表示长期重置每隔多少天自动续推一次。">长期重置间隔（天）</label>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={form.long_term_reset_interval_days}
                  onChange={(e) => updateField('long_term_reset_interval_days', e.target.value)}
                  placeholder="例如：7"
                  title="选填。设置后，长期重置时间到期会自动加上该间隔。"
                />
              </div>
            </div>

            <div className="helper-text">新增时不再要求填写 Slug。系统会根据名称自动生成唯一标识。</div>
            <div className="helper-text">短期重置和长期重置都按北京时间存储与展示；录入时可先选择原始时区。</div>
            <div className="helper-text">如果同时设置了重置时间和重置间隔，到期后系统会自动将该时间向后顺延一轮。</div>

            <div className="form-actions">
              <button type="button" className="btn btn-ghost" onClick={handleCancel} title="关闭表单并放弃当前编辑内容">
                取消
              </button>
              <button type="submit" className="btn btn-primary" disabled={saving || !form.name.trim() || !effectiveAgentType || !form.capability.trim() || (usesCustomModel && !form.custom_model_name.trim())} title="保存当前 Agent 配置">
                {saving ? '保存中...' : editingId ? '更新 Agent' : '创建 Agent'}
              </button>
            </div>
          </form>
        </div>
      )}

      <table className="data-table agents-table">
        <colgroup>
          <col className="agents-col-name" />
          <col className="agents-col-type" />
          <col className="agents-col-model" />
          <col className="agents-col-capability" />
          <col className="agents-col-status" />
          <col className="agents-col-subscription" />
          <col className="agents-col-short-reset" />
          <col className="agents-col-short-interval" />
          <col className="agents-col-long-reset" />
          <col className="agents-col-long-interval" />
          <col className="agents-col-actions" />
        </colgroup>
        <thead>
          <tr>
            <th>名称</th>
            <th>类型</th>
            <th>模型</th>
            <th>能力</th>
            <th>状态</th>
            <th>订阅到期</th>
            <th className="agents-stacked-header">
              <span>短期</span>
              <span>重置</span>
              <span>剩余</span>
              <span>时间</span>
            </th>
            <th>短期间隔</th>
            <th className="agents-stacked-header">
              <span>长期</span>
              <span>重置</span>
              <span>剩余</span>
              <span>时间</span>
            </th>
            <th>长期间隔</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {sortedAgents.map((agent) => {
            const shortTermCountdown = formatCountdown(agent.short_term_reset_at);
            const longTermCountdown = formatCountdown(agent.long_term_reset_at);
            const derivedStatus = deriveAvailabilityStatus(agent);
            const showShortResetActions = Boolean(
              agent.short_term_reset_at
              && agent.short_term_reset_interval_hours
              && agent.short_term_reset_needs_confirmation,
            );
            const showLongResetActions = Boolean(
              agent.long_term_reset_at
              && agent.long_term_reset_interval_days
              && agent.long_term_reset_needs_confirmation,
            );

            // 短期重置：不足1小时为红色
            const shortTermColor = shortTermCountdown.diffMs >= 0 && shortTermCountdown.diffMs < 60 * 60 * 1000 && shortTermCountdown.display !== '-'
              ? '#ef4444' : undefined;
            // 长期重置：不足1天为红色，不足2天为橙黄色
            let longTermColor: string | undefined;
            if (longTermCountdown.display !== '-' && longTermCountdown.diffMs >= 0) {
              if (longTermCountdown.diffMs < 24 * 60 * 60 * 1000) {
                longTermColor = '#ef4444';
              } else if (longTermCountdown.diffMs < 2 * 24 * 60 * 60 * 1000) {
                longTermColor = '#e89a1d';
              }
            }

            return (
              <tr key={agent.id}>
                <td className="agent-name-cell">{agent.name}</td>
                <td className="agent-type-cell">{agent.agent_type}</td>
                <td className="agent-model-cell">{agent.model_name || <span className="text-muted">-</span>}</td>
                <td className="agent-capability-cell">{agent.capability || <span className="text-muted">-</span>}</td>
                <td className="agent-status-cell"><StatusBadge status={derivedStatus} /></td>
                <td className="agent-subscription-cell">
                  {formatBeijingTime(agent.subscription_expires_at)}
                </td>
                <td className="agent-reset-cell">
                  <div className="reset-cell">
                    <div title={shortTermCountdown.tooltip} style={shortTermColor ? { color: shortTermColor, fontWeight: 600 } : undefined}>
                      {shortTermCountdown.display === '-' ? <span className="text-muted">-</span> : shortTermCountdown.display}
                    </div>
                    {showShortResetActions && (
                      <div className="reset-action-row">
                        <button
                          className="btn btn-sm btn-warning"
                          title="点击重置短期剩余时间"
                          onClick={() => handleResetAction(agent.id, 'short')}
                          disabled={actionAgentId === agent.id}
                        >
                          重置
                        </button>
                        <button
                          className="btn btn-sm btn-primary"
                          title="下次短期重置时间无误"
                          onClick={() => handleConfirmAction(agent.id, 'short')}
                          disabled={actionAgentId === agent.id}
                        >
                          确认
                        </button>
                      </div>
                    )}
                  </div>
                </td>
                <td className="agent-interval-cell">{agent.short_term_reset_interval_hours != null ? `${agent.short_term_reset_interval_hours} 小时` : <span className="text-muted">-</span>}</td>
                <td className="agent-reset-cell">
                  <div className="reset-cell">
                    <div title={longTermCountdown.tooltip} style={longTermColor ? { color: longTermColor, fontWeight: 600 } : undefined}>
                      {longTermCountdown.display === '-' ? <span className="text-muted">-</span> : longTermCountdown.display}
                    </div>
                    {showLongResetActions && (
                      <div className="reset-action-row">
                        <button
                          className="btn btn-sm btn-warning"
                          title="点击重置长期剩余时间"
                          onClick={() => handleResetAction(agent.id, 'long')}
                          disabled={actionAgentId === agent.id}
                        >
                          重置
                        </button>
                        <button
                          className="btn btn-sm btn-primary"
                          title="下次长期重置时间无误"
                          onClick={() => handleConfirmAction(agent.id, 'long')}
                          disabled={actionAgentId === agent.id}
                        >
                          确认
                        </button>
                      </div>
                    )}
                  </div>
                </td>
                <td className="agent-interval-cell">{agent.long_term_reset_interval_days != null ? `${agent.long_term_reset_interval_days} 天` : <span className="text-muted">-</span>}</td>
                <td className="agent-operations-cell">
                  <div className="agent-actions-cell">
                    <button className="btn btn-sm btn-ghost" onClick={() => handleEdit(agent)} title="编辑当前智能体的配置信息">
                      编辑
                    </button>
                    <button className="btn btn-sm btn-danger" onClick={() => handleDelete(agent)} disabled={deletingId === agent.id} title="删除当前智能体">
                      {deletingId === agent.id ? '删除中...' : '删除'}
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
          {agents.length === 0 && (
            <tr>
              <td colSpan={11} className="empty-row">当前还没有配置智能体。</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
