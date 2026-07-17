import React from 'react';
import { api, extractApiErrorDetail } from '../api/client';

interface Experiment { experiment_id: string; max_attempts: number; feedback_mode: string }
interface Arm { arm_id: string; label: string; include_fields: string[]; omitted_fields: string[] }
interface EvaluationSummary {
  resolved: boolean;
  public: { passed: number; total: number };
  hidden: { passed: number; total: number; failed_test_ids: string[] };
  changed_files: string[];
}
interface LeakageAudit {
  status: 'passed' | 'failed' | 'unknown';
  trace_complete: boolean;
  trace_reason?: string | null;
  match_count: number;
}
interface EventCounts {
  file_read_events?: number;
  unique_files_read?: number;
  search_events?: number;
  repeated_search_events?: number;
  test_runs?: number;
  edit_events?: number;
  interface_guess_events?: number;
  ineffective_edit_attempts?: number;
  rollback_events?: number;
  pre_edit_discovery_events?: number;
}
interface Attempt {
  attempt_number: number;
  session_id: string | null;
  usage: { total_tokens: number };
  evaluation: EvaluationSummary;
  trace: { source: string; complete: boolean; reason?: string | null };
  leakage_audit: LeakageAudit;
  event_table: { counts: EventCounts };
}
interface RunMetrics {
  first_attempt_resolved: boolean;
  final_resolved: boolean;
  interaction_rounds: number;
  rework_count: number;
  human_intervention_count: number;
  infra_retry_count: number;
  token_total: number;
  attempt_limit_reached: boolean;
}
interface ExperimentRun {
  run_id: string;
  experiment_id: string;
  arm_id: string;
  arm_label: string;
  visible_fields: string[];
  omitted_fields: string[];
  model: string;
  status: string;
  workspace: string;
  attempts: Attempt[];
  contaminated: boolean;
  excluded_from_analysis: boolean;
  exclusion_reason?: string | null;
  leakage_audit: LeakageAudit;
  event_table: { totals: EventCounts };
  input_integrity_verified: boolean;
  metrics: RunMetrics;
  repair_prompt?: string | null;
}
interface RunPrompt { run_id: string; arm_id: string; workspace: string; prompt: string }

const EMPTY_TOKENS = {
  input_tokens: '0',
  cached_input_tokens: '0',
  output_tokens: '0',
  reasoning_tokens: '0',
  total_tokens: '0',
};

function integer(value: string): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

export default function HandoffExperimentsPage() {
  const [experiments, setExperiments] = React.useState<Experiment[]>([]);
  const [arms, setArms] = React.useState<Arm[]>([]);
  const [experimentId, setExperimentId] = React.useState('');
  const [armId, setArmId] = React.useState('A_full');
  const [model, setModel] = React.useState('gpt-5.5');
  const [run, setRun] = React.useState<ExperimentRun | null>(null);
  const [runPrompt, setRunPrompt] = React.useState<RunPrompt | null>(null);
  const [conversationId, setConversationId] = React.useState('');
  const [tokens, setTokens] = React.useState(EMPTY_TOKENS);
  const [agentOutput, setAgentOutput] = React.useState('');
  const [traceJsonl, setTraceJsonl] = React.useState('');
  const [traceComplete, setTraceComplete] = React.useState(false);
  const [notes, setNotes] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    Promise.all([
      api.get<Experiment[]>('/api/handoff-experiments'),
      api.get<Arm[]>('/api/handoff-experiments/arms'),
    ])
      .then(([loadedExperiments, loadedArms]) => {
        setExperiments(loadedExperiments);
        setArms(loadedArms);
        if (loadedExperiments.length) {
          setExperimentId(loadedExperiments[loadedExperiments.length - 1].experiment_id);
        }
      })
      .catch((err) => setError(extractApiErrorDetail(String(err)) || String(err)));
  }, []);

  async function loadPrompt(nextRun: ExperimentRun) {
    setRunPrompt(await api.get<RunPrompt>(`/api/handoff-experiments/runs/${nextRun.run_id}/prompt`));
  }

  async function prepare() {
    if (!experimentId) return;
    setBusy(true);
    setError('');
    try {
      const nextRun = await api.post<ExperimentRun>(
        `/api/handoff-experiments/${experimentId}/runs`,
        { arm_id: armId, model, max_attempts: 3 },
      );
      setRun(nextRun);
      setConversationId('');
      setTokens(EMPTY_TOKENS);
      setAgentOutput('');
      setTraceJsonl('');
      setTraceComplete(false);
      setNotes('');
      await loadPrompt(nextRun);
    } catch (err) {
      setError(extractApiErrorDetail(String(err)) || String(err));
    } finally {
      setBusy(false);
    }
  }

  async function refresh() {
    if (!run) return;
    setBusy(true);
    try {
      setRun(await api.get<ExperimentRun>(`/api/handoff-experiments/runs/${run.run_id}`));
    } catch (err) {
      setError(extractApiErrorDetail(String(err)) || String(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitAttempt() {
    if (!run) return;
    setBusy(true);
    setError('');
    try {
      const nextRun = await api.post<ExperimentRun>(
        `/api/handoff-experiments/runs/${run.run_id}/attempts`,
        {
          conversation_id: conversationId || null,
          usage: Object.fromEntries(Object.entries(tokens).map(([key, value]) => [key, integer(value)])),
          notes,
          agent_output: agentOutput,
          trace_jsonl: traceJsonl,
          trace_complete: traceComplete,
        },
      );
      setRun(nextRun);
      setTokens(EMPTY_TOKENS);
      setTraceJsonl('');
      setTraceComplete(false);
      setNotes('');
    } catch (err) {
      setError(extractApiErrorDetail(String(err)) || String(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveRunUsage() {
    if (!run) return;
    setBusy(true);
    setError('');
    try {
      const nextRun = await api.patch<ExperimentRun>(
        `/api/handoff-experiments/runs/${run.run_id}/usage`,
        Object.fromEntries(Object.entries(tokens).map(([key, value]) => [key, integer(value)])),
      );
      setRun(nextRun);
    } catch (err) {
      setError(extractApiErrorDetail(String(err)) || String(err));
    } finally {
      setBusy(false);
    }
  }

  async function copyPrompt() {
    if (!runPrompt) return;
    await navigator.clipboard.writeText(runPrompt.prompt);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  const latestAttempt = run && run.attempts.length
    ? run.attempts[run.attempts.length - 1]
    : undefined;
  const eventTotals = run?.event_table?.totals || {};

  return (
    <div className="handoff-lab-page">
      <header className="handoff-lab-header">
        <div>
          <h1>Handoff 字段消融实验</h1>
          <p>HALF 负责过滤 handoff、冻结实验输入、运行隐藏评测并归档审计证据。</p>
        </div>
        {run && <button className="btn btn-secondary" onClick={refresh} disabled={busy}>刷新运行</button>}
      </header>

      {error && <div className="error-message">{error}</div>}

      <section className="handoff-lab-band">
        <h2>创建校准运行</h2>
        <div className="handoff-lab-form-grid">
          <label>实验<select value={experimentId} onChange={(event) => setExperimentId(event.target.value)}>{experiments.map((item) => <option key={item.experiment_id}>{item.experiment_id}</option>)}</select></label>
          <label>实验组<select value={armId} onChange={(event) => setArmId(event.target.value)}>{arms.map((arm) => <option key={arm.arm_id} value={arm.arm_id}>{arm.arm_id} · {arm.label}</option>)}</select></label>
          <label>Codex 模型<input value={model} onChange={(event) => setModel(event.target.value)} /></label>
          <button className="btn btn-primary handoff-lab-create" onClick={prepare} disabled={busy || !experimentId}>{busy ? '处理中...' : '生成独立运行'}</button>
        </div>
      </section>

      {run && runPrompt && (
        <>
          <section className="handoff-lab-band">
            <div className="handoff-lab-section-heading">
              <div><h2>{run.arm_id}</h2><p className="mono">Run: {run.run_id}</p></div>
              <span className={`handoff-run-status status-${run.status}`}>{run.status}</span>
            </div>
            {run.excluded_from_analysis && <div className="error-message">该 run 已从分析排除：{run.exclusion_reason}</div>}
            <dl className="handoff-run-facts">
              <div><dt>工作目录</dt><dd className="mono">{run.workspace}</dd></div>
              <div><dt>可见字段</dt><dd>{run.visible_fields.join(', ') || '无'}</dd></div>
              <div><dt>删除字段</dt><dd>{run.omitted_fields.join(', ') || '无'}</dd></div>
              <div><dt>输入冻结</dt><dd>{run.input_integrity_verified ? '已记录哈希' : '未记录'}</dd></div>
            </dl>
            <div className="handoff-prompt-heading"><h3>发给新 Codex 对话的 Prompt</h3><button className="btn btn-secondary" onClick={copyPrompt}>{copied ? '已复制' : '复制 Prompt'}</button></div>
            <textarea className="handoff-prompt" value={runPrompt.prompt} readOnly />
          </section>

          <section className="handoff-lab-band">
            <h2>提交本轮 Attempt</h2>
            <div className="handoff-attempt-grid">
              <label>对话 ID<input value={conversationId} onChange={(event) => setConversationId(event.target.value)} /></label>
            </div>
            <p>Token 将根据对话 ID 从 Codex Trace 自动采集，无需手动填写。</p>
            <label className="handoff-wide-field">Agent 最终输出（用于审计）<textarea value={agentOutput} onChange={(event) => setAgentOutput(event.target.value)} /></label>
            <label className="handoff-wide-field">Tool Trace JSONL（可选，系统优先按对话 ID 自动读取）<textarea value={traceJsonl} onChange={(event) => setTraceJsonl(event.target.value)} /></label>
            {traceJsonl.trim() && <label><input type="checkbox" checked={traceComplete} onChange={(event) => setTraceComplete(event.target.checked)} /> 手工 Trace 已覆盖本轮全部可见输入与工具调用</label>}
            <label className="handoff-wide-field">备注<input value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
            <div className="handoff-attempt-actions">
              <button className="btn btn-primary" onClick={submitAttempt} disabled={busy || run.status === 'resolved' || run.status === 'failed'}>运行隐藏评测并提交</button>
            </div>
            <details className="handoff-token-fallback">
              <summary>自动采集失败时手动补录 Token</summary>
              <div className="handoff-attempt-grid">
                {Object.entries(tokens).map(([key, value]) => <label key={key}>{key}<input type="number" min="0" value={value} onChange={(event) => setTokens((current) => ({ ...current, [key]: event.target.value }))} /></label>)}
              </div>
              <button className="btn btn-secondary" onClick={saveRunUsage} disabled={busy || run.attempts.length === 0 || integer(tokens.total_tokens) <= 0}>仅保存 Token（不运行评测）</button>
            </details>
          </section>

          <section className="handoff-lab-band">
            <h2>运行结果</h2>
            <div className="handoff-metrics-row">
              <div><strong>{run.metrics.interaction_rounds}</strong><span>交互轮数</span></div>
              <div><strong>{run.metrics.rework_count}</strong><span>返工次数</span></div>
              <div><strong>{run.metrics.token_total}</strong><span>Token</span></div>
              <div><strong>{run.metrics.human_intervention_count}</strong><span>人工干预</span></div>
            </div>
            {run.metrics.attempt_limit_reached && <div className="error-message">本次运行已达到最大尝试次数；返工次数是上限截断值。</div>}
            {latestAttempt && <div className="handoff-evaluation"><p>公开测试：{latestAttempt.evaluation.public.passed}/{latestAttempt.evaluation.public.total}</p><p>隐藏测试：{latestAttempt.evaluation.hidden.passed}/{latestAttempt.evaluation.hidden.total}</p><p>变更文件：{latestAttempt.evaluation.changed_files.join(', ') || '无'}</p>{latestAttempt.evaluation.hidden.failed_test_ids.length > 0 && <p>失败探针：{latestAttempt.evaluation.hidden.failed_test_ids.join(', ')}</p>}</div>}
            <div className="handoff-evaluation">
              <p><strong>泄漏审计：{run.leakage_audit.status}</strong></p>
              <p>本轮 Trace：{latestAttempt?.trace.complete ? '完整' : '不完整'}{latestAttempt?.trace.reason ? `（${latestAttempt.trace.reason}）` : ''}</p>
              <p>删字段命中：{run.leakage_audit.match_count || 0}</p>
            </div>
            <div className="handoff-evaluation">
              <p><strong>Trace 事件累计</strong></p>
              <p>读文件 {eventTotals.file_read_events || 0} 次（{eventTotals.unique_files_read || 0} 个唯一文件）；搜索 {eventTotals.search_events || 0} 次；重复搜索 {eventTotals.repeated_search_events || 0} 次。</p>
              <p>测试 {eventTotals.test_runs || 0} 次；编辑 {eventTotals.edit_events || 0} 次；接口猜测 {eventTotals.interface_guess_events || 0} 次；无效编辑轮 {eventTotals.ineffective_edit_attempts || 0}；回滚 {eventTotals.rollback_events || 0} 次。</p>
            </div>
            {run.repair_prompt && <label className="handoff-wide-field">发回同一对话的修复 Prompt<textarea value={run.repair_prompt} readOnly /></label>}
            {run.contaminated && <div className="error-message">泄漏审计检测到被删除字段内容，本运行已污染。</div>}
          </section>
        </>
      )}
    </div>
  );
}
