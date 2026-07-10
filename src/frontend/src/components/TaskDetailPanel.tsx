import React, { useEffect, useMemo, useState } from 'react';
import { Task, Agent, FlowState } from '../types';
import { api } from '../api/client';
import StatusBadge from './StatusBadge';
import { copyText } from '../contracts';
import { formatDateTime } from '../utils/datetime';
import { ISSUE_REVIEW_LOOP_ATTENTION_MESSAGE, isIssueReviewLoopAttentionTask } from '../utils/issueReviewLoop';

interface Props {
  task: Task;
  agents: Agent[];
  allTasks: Task[];
  flowState?: FlowState | null;
  onRefresh: () => void;
}

interface HandoffArm {
  arm_id: string;
  label: string;
  description: string;
  format: string;
  include_fields: string[];
}

const FALLBACK_HANDOFF_ARMS: HandoffArm[] = [
  {
    arm_id: 'A_full',
    label: '完整组',
    description: '注入最小 schema 的全部 6 个字段，作为基线。',
    format: 'structured',
    include_fields: ['goal', 'changed_files', 'verification', 'unfinished_items', 'risks', 'next_steps'],
  },
  {
    arm_id: 'B_no_verification',
    label: '去掉验证证据',
    description: '不注入 verification 字段。',
    format: 'structured',
    include_fields: ['goal', 'changed_files', 'unfinished_items', 'risks', 'next_steps'],
  },
  {
    arm_id: 'C_no_unfinished_items',
    label: '去掉未完成项',
    description: '不注入 unfinished_items 字段。',
    format: 'structured',
    include_fields: ['goal', 'changed_files', 'verification', 'risks', 'next_steps'],
  },
  {
    arm_id: 'D_no_risks',
    label: '去掉风险/约束',
    description: '不注入 risks 字段。',
    format: 'structured',
    include_fields: ['goal', 'changed_files', 'verification', 'unfinished_items', 'next_steps'],
  },
  {
    arm_id: 'E_summary_only',
    label: '只给自然语言摘要',
    description: '不暴露结构化字段名，只注入一段摘要。',
    format: 'summary',
    include_fields: ['goal', 'changed_files', 'verification', 'unfinished_items', 'risks', 'next_steps'],
  },
  {
    arm_id: 'F_full_context',
    label: '给全文上下文',
    description: '注入前序 handoff.json 与 result.json 原文。',
    format: 'full_context',
    include_fields: ['goal', 'changed_files', 'verification', 'unfinished_items', 'risks', 'next_steps'],
  },
];

export default function TaskDetailPanel({ task, agents, allTasks, flowState, onRefresh }: Props) {
  const [loading, setLoading] = useState('');
  const [copied, setCopied] = useState(false);
  const [showDispatchReminder, setShowDispatchReminder] = useState(false);
  const dispatchReminderRef = React.useRef<number | null>(null);
  const [draftTaskName, setDraftTaskName] = useState(task.task_name);
  const [draftDescription, setDraftDescription] = useState(task.description || '');
  const [draftExpectedOutput, setDraftExpectedOutput] = useState(task.expected_output_path || '');
  const [draftTimeoutMinutes, setDraftTimeoutMinutes] = useState(String(task.timeout_minutes ?? 10));
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  // 预取的 Prompt。派发按钮在点击瞬间需要把 Prompt 同步写入剪贴板
  // （以保留浏览器的 user activation），所以不能等到点击之后再去 await
  // /generate-prompt —— 那会让 navigator.clipboard.writeText 因为 activation
  // 失效而静默失败，导致剪贴板里残留上一次成功复制的 Prompt。
  const [cachedPrompt, setCachedPrompt] = useState<string | null>(null);
  const [promptError, setPromptError] = useState<string | null>(null);
  const [handoffArms, setHandoffArms] = useState<HandoffArm[]>(FALLBACK_HANDOFF_ARMS);
  const [selectedHandoffArmId, setSelectedHandoffArmId] = useState('');

  const assignee = agents.find((a) => a.id === task.assignee_agent_id);

  let deps: string[] = [];
  try {
    deps = JSON.parse(task.depends_on_json || '[]');
  } catch {
    deps = [];
  }
  const predecessorTasks = allTasks.filter((t) => deps.includes(t.task_code));
  const blockedPredecessors = predecessorTasks.filter(
    (predecessorTask) => predecessorTask.status !== 'completed' && predecessorTask.status !== 'abandoned'
  );
  const businessState = flowState?.enabled ? (flowState.effective_task_states?.[task.task_code] || 'frozen') : null;
  const businessDispatchable = businessState === 'unlocked' || businessState === 'needs_fix';
  const loopTaskRunning = Boolean(flowState?.enabled && task.status === 'running');
  const canLoopRedispatch = Boolean(flowState?.enabled && businessDispatchable && task.status === 'running');
  const canOperate = flowState?.enabled ? (businessDispatchable && !loopTaskRunning) : blockedPredecessors.length === 0;
  const canPreparePrompt = flowState?.enabled ? (businessDispatchable || canLoopRedispatch) : blockedPredecessors.length === 0;
  const canEdit = !flowState?.enabled && task.status === 'pending' && canOperate;
  const showIssueReviewLoopAttention = isIssueReviewLoopAttentionTask(task, flowState);
  const selectedHandoffArm = handoffArms.find((arm) => arm.arm_id === selectedHandoffArmId) || null;

  useEffect(() => {
    void api.getCached<HandoffArm[]>('/api/handoff-arms', (value) => {
      if (Array.isArray(value) && value.length > 0) {
        setHandoffArms(value);
      }
    });
  }, []);

  useEffect(() => {
    setDraftTaskName(task.task_name);
    setDraftDescription(task.description || '');
    setDraftExpectedOutput(task.expected_output_path || '');
    setDraftTimeoutMinutes(String(task.timeout_minutes ?? 10));
    setSaveState('idle');
  }, [task.description, task.expected_output_path, task.id, task.task_name, task.timeout_minutes]);

  const parsedDraftTimeoutMinutes = Number.parseInt(draftTimeoutMinutes, 10);
  const isDraftTimeoutValid = Number.isInteger(parsedDraftTimeoutMinutes)
    && parsedDraftTimeoutMinutes >= 1
    && parsedDraftTimeoutMinutes <= 120;

  const normalizedDraft = useMemo(() => ({
    task_name: draftTaskName.trim(),
    description: draftDescription,
    expected_output_path: draftExpectedOutput,
    timeout_minutes: parsedDraftTimeoutMinutes,
  }), [draftDescription, draftExpectedOutput, draftTaskName, parsedDraftTimeoutMinutes]);
  const hasDraftChanges = canEdit && (
    normalizedDraft.task_name !== task.task_name
    || normalizedDraft.description !== (task.description || '')
    || normalizedDraft.expected_output_path !== (task.expected_output_path || '')
    || normalizedDraft.timeout_minutes !== task.timeout_minutes
  );

  useEffect(() => {
    if (!canEdit) return undefined;
    if (!hasDraftChanges) {
      return undefined;
    }
    if (!isDraftTimeoutValid) {
      setSaveState('error');
      return undefined;
    }

    setSaveState('saving');
    const timer = window.setTimeout(async () => {
      try {
        await api.put(`/api/tasks/${task.id}`, normalizedDraft);
        setSaveState('saved');
        onRefresh();
      } catch {
        setSaveState('error');
      }
    }, 600);

    return () => window.clearTimeout(timer);
  }, [canEdit, hasDraftChanges, isDraftTimeoutValid, normalizedDraft, onRefresh, task.description, task.expected_output_path, task.id, task.task_name]);

  useEffect(() => {
    if (saveState !== 'saved') return undefined;
    const timer = window.setTimeout(() => setSaveState('idle'), 1200);
    return () => window.clearTimeout(timer);
  }, [saveState]);

  // 在切换到一个可派发的任务时立即预取 Prompt，存到本地 state；
  // 这样用户点击「复制 Prompt 并派发 / 重新派发」时可以同步写剪贴板。
  // 任务的关键字段（描述、预期输出）变化时也要重新拉取。
  useEffect(() => {
    setCachedPrompt(null);
    setPromptError(null);
    if (!canPreparePrompt) return undefined;
    if (hasDraftChanges) return undefined;
    if (flowState?.enabled) {
      if (!businessDispatchable) return undefined;
    } else if (!['pending', 'needs_attention', 'running'].includes(task.status)) {
      return undefined;
    }

    let cancelled = false;
    api.post<{ prompt: string }>(
      `/api/tasks/${task.id}/generate-prompt`,
      { include_usage: false, handoff_arm_id: selectedHandoffArmId || null },
    )
      .then((resp) => {
        if (cancelled) return;
        setCachedPrompt(resp.prompt);
      })
      .catch((err) => {
        if (cancelled) return;
        setPromptError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [task.id, task.status, task.task_name, task.description, task.expected_output_path, canPreparePrompt, hasDraftChanges, flowState?.enabled, businessDispatchable, selectedHandoffArmId]);

  async function performDispatch(action: 'dispatch' | 'redispatch') {
    const actionAllowed = action === 'redispatch' && flowState?.enabled ? canLoopRedispatch : canOperate;
    if (!actionAllowed) {
      alert(`前序任务尚未全部完成，无法派发：${blockedPredecessors.map((taskItem) => taskItem.task_code).join(', ')}`);
      return;
    }
    if (!cachedPrompt) {
      alert(promptError
        ? `Prompt 生成失败，已取消派发：${promptError}`
        : 'Prompt 仍在准备中，请稍候再点击。');
      return;
    }

    // 关键：在任何 await 之前同步把剪贴板写入操作发出去。
    // copyText 内部第一行就同步调用 clipboard.writeText(...)，所以浏览器
    // 在判定 user activation 时仍处于点击触发的同步执行栈中。
    // 如果这里复制失败，必须显式抛错并中止派发，绝不能让用户拿到一个
    // 「显示已复制但剪贴板里其实是上一次内容」的错觉。
    let copyOk = false;
    try {
      copyOk = await copyText(cachedPrompt, navigator.clipboard);
    } catch (err) {
      alert(`复制 Prompt 到剪贴板失败，已取消派发：${err}`);
      return;
    }
    if (!copyOk) {
      alert('复制 Prompt 到剪贴板失败，已取消派发。请确认浏览器允许剪贴板权限后重试。');
      return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);

    setLoading(action);
    try {
      await api.post(`/api/tasks/${task.id}/${action}`, {
        ignore_missing_predecessor_outputs: false,
        handoff_arm_id: selectedHandoffArmId || null,
      });
      setShowDispatchReminder(false);
      if (dispatchReminderRef.current) clearTimeout(dispatchReminderRef.current);
      dispatchReminderRef.current = window.setTimeout(() => setShowDispatchReminder(true), 5 * 60 * 1000);
      onRefresh();
    } catch (err) {
      alert(`派发失败：${err}`);
    } finally {
      setLoading('');
    }
  }

  async function handleCopyPrompt() {
    await performDispatch('dispatch');
  }

  async function handleRedispatch() {
    await performDispatch('redispatch');
  }

  async function handleMarkComplete() {
    setLoading('complete');
    try {
      await api.post(`/api/tasks/${task.id}/mark-complete`);
      onRefresh();
    } catch (err) {
      alert(`手动完成失败：${err}`);
    } finally {
      setLoading('');
    }
  }

  async function handleAbandon() {
    if (!canOperate) {
      alert(`前序任务尚未全部完成，当前不能放弃：${blockedPredecessors.map((taskItem) => taskItem.task_code).join(', ')}`);
      return;
    }
    if (!confirm('确认放弃这个任务吗？该操作会记录为人工干预。')) return;
    setLoading('abandon');
    try {
      await api.post(`/api/tasks/${task.id}/abandon`);
      onRefresh();
    } catch (err) {
      alert(`放弃任务失败：${err}`);
    } finally {
      setLoading('');
    }
  }

  return (
    <div className="task-detail-panel">
      <h3>{task.task_code}: {task.task_name}</h3>
      <StatusBadge status={task.status} />
      {businessState && (
        <div className="detail-section">
          <label>流程业务状态</label>
          <p><StatusBadge status={businessState} /></p>
        </div>
      )}

      {showIssueReviewLoopAttention && (
        <div className="helper-text helper-text-warning">
          {ISSUE_REVIEW_LOOP_ATTENTION_MESSAGE}
        </div>
      )}

      <div className="detail-section">
        <label>指派 Agent</label>
        <p>{assignee ? `${assignee.name} (${assignee.agent_type}${assignee.model_name ? ` / ${assignee.model_name}` : ''})` : (task.assignee_agent_id ? `Agent #${task.assignee_agent_id}` : '未指派')}</p>
      </div>

      <div className="detail-section">
        <label>前置依赖</label>
        {predecessorTasks.length === 0 ? (
          <p>无</p>
        ) : (
          <ul className="dep-list">
            {predecessorTasks.map((pt) => (
              <li key={pt.id}>
                <span className="dep-code">{pt.task_code}</span> - {pt.task_name}
                {pt.result_file_path && (
                  <span className="dep-output">（输出文件：{pt.result_file_path}）</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="detail-section handoff-experiment-section">
        <label>Handoff 实验组</label>
        <select
          value={selectedHandoffArmId}
          onChange={(event) => setSelectedHandoffArmId(event.target.value)}
          className="detail-select"
          title="选择后，生成的任务 Prompt 会按该消融组注入前序 handoff.json"
        >
          <option value="">不启用（普通任务）</option>
          {handoffArms.map((arm) => (
            <option key={arm.arm_id} value={arm.arm_id}>
              {arm.arm_id} - {arm.label}
            </option>
          ))}
        </select>
        {selectedHandoffArm ? (
          <div className="helper-text">
            {selectedHandoffArm.description} 可见字段：{selectedHandoffArm.include_fields.join(', ') || '无'}
          </div>
        ) : (
          <div className="helper-text">
            不启用时沿用普通 HALF prompt，不读取前序 handoff.json。
          </div>
        )}
      </div>

      <div className="detail-section">
        <label>任务名称</label>
        {canEdit ? (
          <input
            value={draftTaskName}
            onChange={(event) => setDraftTaskName(event.target.value)}
            className="detail-input"
            placeholder="请输入任务名称"
          />
        ) : (
          <p>{task.task_name}</p>
        )}
      </div>

      <div className="detail-section">
        <label>任务描述</label>
        {canEdit ? (
          <textarea
            value={draftDescription}
            onChange={(event) => setDraftDescription(event.target.value)}
            rows={5}
            className="detail-textarea"
            placeholder="请输入任务描述"
          />
        ) : (
          <p>{task.description || '暂无描述'}</p>
        )}
      </div>

      <div className="detail-section">
        <label>预期输出</label>
        {canEdit ? (
          <textarea
            value={draftExpectedOutput}
            onChange={(event) => setDraftExpectedOutput(event.target.value)}
            rows={3}
            className="detail-textarea"
            placeholder="请输入预期输出"
          />
        ) : (
          <p>{task.expected_output_path || '暂无描述'}</p>
        )}
      </div>

      {canEdit && (
        <div className={`helper-text ${saveState === 'error' ? 'helper-text-error' : ''}`}>
          {saveState === 'saving' && '正在自动保存...'}
          {saveState === 'saved' && '已自动保存'}
          {saveState === 'error' && '自动保存失败，请稍后重试'}
          {saveState === 'idle' && '修改右侧文本后会自动保存'}
        </div>
      )}

      {task.result_file_path && (
        <div className="detail-section">
          <label>结果文件</label>
          <p>{task.result_file_path}</p>
        </div>
      )}

      {task.last_error && (
        <div className="detail-section error-section">
          <label>最近错误</label>
          <p className="error-text">{task.last_error}</p>
        </div>
      )}

      <div className="detail-section">
        <label>超时时间</label>
        {canEdit ? (
          <>
            <input
              type="number"
              min="1"
              max="120"
              value={draftTimeoutMinutes}
              onChange={(event) => setDraftTimeoutMinutes(event.target.value)}
              className="detail-input"
            />
            <div className={`helper-text ${!isDraftTimeoutValid ? 'helper-text-error' : ''}`}>
              范围：1-120 分钟
            </div>
          </>
        ) : (
          <p>{task.timeout_minutes} 分钟</p>
        )}
      </div>

      {task.dispatched_at && (
        <div className="detail-section">
          <label>派发时间</label>
          <p>{formatDateTime(task.dispatched_at)}</p>
        </div>
      )}

      {task.completed_at && (
        <div className="detail-section">
          <label>完成时间</label>
          <p>{formatDateTime(task.completed_at)}</p>
        </div>
      )}

      <div className="detail-actions">
        {((flowState?.enabled && businessDispatchable && task.status !== 'running') || (!flowState?.enabled && (task.status === 'pending' || task.status === 'needs_attention'))) && (
          <div className="copy-prompt-row">
            <button
              className="btn btn-primary"
              onClick={handleCopyPrompt}
              disabled={loading === 'dispatch' || !canOperate || !cachedPrompt}
              title="生成当前任务的 Prompt，复制到剪贴板，并同步派发任务"
            >
              {copied
                ? 'Prompt 已复制'
                : cachedPrompt
                  ? '复制 Prompt 并派发'
                  : (promptError ? 'Prompt 生成失败' : 'Prompt 准备中...')}
            </button>
          </div>
        )}

        {showDispatchReminder && task.status === 'running' && (
          <div className="helper-text helper-text-warning">
            已超过 5 分钟未检测到 Git 变更，是否已将 Prompt 发送给 Agent？
          </div>
        )}

        {!canOperate && !canLoopRedispatch && (flowState?.enabled || task.status === 'pending' || task.status === 'needs_attention') && (
          <div className="helper-text helper-text-error">
            {flowState?.enabled
              ? `当前流程业务状态为 ${businessState || 'unknown'}，不能复制 Prompt 或派发。`
              : '前序任务未全部完成，当前不能复制 Prompt 或放弃任务。'}
          </div>
        )}

        {((flowState?.enabled && canLoopRedispatch) || (!flowState?.enabled && (task.status === 'running' || task.status === 'needs_attention'))) && (
          <button
            className="btn btn-secondary"
            onClick={handleRedispatch}
            disabled={loading === 'redispatch' || !cachedPrompt}
            title="重新生成当前任务的 Prompt，复制到剪贴板，并重新派发"
          >
            {loading === 'redispatch'
              ? '派发中...'
              : copied
                ? 'Prompt 已复制'
                : cachedPrompt
                  ? '重新派发'
                  : (promptError ? 'Prompt 生成失败' : 'Prompt 准备中...')}
          </button>
        )}

        {(task.status === 'running' || task.status === 'needs_attention') && (
          <button
            className="btn btn-success"
            onClick={handleMarkComplete}
            disabled={loading === 'complete'}
            title="在人工确认结果无误后，手动将任务标记为完成"
          >
            标记完成
          </button>
        )}

        {task.status !== 'completed' && task.status !== 'abandoned' && (
          <button
            className="btn btn-danger"
            onClick={handleAbandon}
            disabled={loading === 'abandon' || !canOperate}
            title="放弃当前任务，并在系统中记录人工干预"
          >
            放弃任务
          </button>
        )}
      </div>
    </div>
  );
}
