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

function formatForDateTimeLocal(value: string | null | undefined) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
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

function convertToBeijingIso(localValue: string, timezoneCode: string) {
  if (!localValue) return null;
  const parsed = parseDateTimeLocal(localValue);
  if (!parsed) return null;
  const timezone = TIMEZONE_OPTIONS.find((option) => option.value === timezoneCode) || TIMEZONE_OPTIONS[0];
  const utcMillis = Date.UTC(parsed.year, parsed.month - 1, parsed.day, parsed.hour, parsed.minute) - timezone.offsetMinutes * 60 * 1000;
  return new Date(utcMillis).toISOString();
}

function formatBeijingPreview(localValue: string, timezoneCode: string) {
  const isoValue = convertToBeijingIso(localValue, timezoneCode);
  if (!isoValue) return '未设置';
  return new Date(isoValue).toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    hour12: false,
  });
}

function formatBeijingTime(value: string | null | undefined) {
  if (!value) return <span className="text-muted">-</span>;
  return new Date(value).toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    hour12: false,
  });
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<AgentForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState('');

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
      short_term_reset_at: formatForDateTimeLocal(agent.short_term_reset_at),
      short_term_reset_timezone: 'CST',
      short_term_reset_interval_hours: agent.short_term_reset_interval_hours != null ? String(agent.short_term_reset_interval_hours) : '',
      long_term_reset_at: formatForDateTimeLocal(agent.long_term_reset_at),
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
        machine_label: form.machine_label.trim() || null,
        capability: form.capability.trim() || null,
        subscription_expires_at: form.subscription_expires_at || null,
        short_term_reset_at: convertToBeijingIso(form.short_term_reset_at, form.short_term_reset_timezone),
        short_term_reset_interval_hours: form.short_term_reset_interval_hours.trim() ? Number(form.short_term_reset_interval_hours) : null,
        long_term_reset_at: convertToBeijingIso(form.long_term_reset_at, form.long_term_reset_timezone),
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

  if (loading) return <div className="page-loading">正在加载 Agents...</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Agents</h1>
        <button className="btn btn-primary" onClick={handleAdd} title="新增一个可用于项目执行的 Agent">
          新增 Agent
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

            <div className="form-row compact-form-row">
              <div className="form-group">
                <label title="可选，用于区分 Agent 运行在哪台设备上。">机器标识</label>
                <input
                  type="text"
                  value={form.machine_label}
                  onChange={(e) => updateField('machine_label', e.target.value)}
                  placeholder="例如：macbook-1"
                  title="选填，用于排查和调度。"
                />
              </div>
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

      <table className="data-table">
        <thead>
          <tr>
            <th>名称</th>
            <th>类型</th>
            <th>模型</th>
            <th>能力</th>
            <th>状态</th>
            <th>订阅到期</th>
            <th>短期重置</th>
            <th>短期间隔</th>
            <th>长期重置</th>
            <th>长期间隔</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {agents.map((agent) => (
            <tr key={agent.id}>
              <td className="agent-name-cell">{agent.name}</td>
              <td>{agent.agent_type}</td>
              <td>{agent.model_name || <span className="text-muted">-</span>}</td>
              <td>{agent.capability || <span className="text-muted">-</span>}</td>
              <td><StatusBadge status={agent.availability_status} /></td>
              <td>
                {formatBeijingTime(agent.subscription_expires_at)}
              </td>
              <td>{formatBeijingTime(agent.short_term_reset_at)}</td>
              <td>{agent.short_term_reset_interval_hours != null ? `${agent.short_term_reset_interval_hours} 小时` : <span className="text-muted">-</span>}</td>
              <td>{formatBeijingTime(agent.long_term_reset_at)}</td>
              <td>{agent.long_term_reset_interval_days != null ? `${agent.long_term_reset_interval_days} 天` : <span className="text-muted">-</span>}</td>
              <td>
                <div className="agent-actions-cell">
                  <button className="btn btn-sm btn-ghost" onClick={() => handleEdit(agent)} title="编辑当前 Agent 的配置信息">
                    编辑
                  </button>
                  <button className="btn btn-sm btn-danger" onClick={() => handleDelete(agent)} disabled={deletingId === agent.id} title="删除当前 Agent">
                    {deletingId === agent.id ? '删除中...' : '删除'}
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {agents.length === 0 && (
            <tr>
              <td colSpan={11} className="empty-row">当前还没有配置 Agent。</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
