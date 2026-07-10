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
interface Attempt {
  attempt_number: number;
  session_id: string | null;
  usage: { total_tokens: number };
  evaluation: EvaluationSummary;
}
interface RunMetrics {
  first_attempt_resolved: boolean;
  final_resolved: boolean;
  interaction_rounds: number;
  rework_count: number;
  human_intervention_count: number;
  infra_retry_count: number;
  token_total: number;
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
        if (loadedExperiments.length) setExperimentId(loadedExperiments[0].experiment_id);
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
        },
      );
      setRun(nextRun);
      setTokens(EMPTY_TOKENS);
      setNotes('');
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

  return (
    <div className="handoff-lab-page">
      <header className="handoff-lab-header">
        <div>
          <h1>Handoff 字段消融实验</h1>
          <p>每个运行使用新的 Codex 对话；HALF 负责过滤 handoff、隐藏评测和多轮指标。</p>
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
            <dl className="handoff-run-facts">
              <div><dt>工作目录</dt><dd className="mono">{run.workspace}</dd></div>
              <div><dt>可见字段</dt><dd>{run.visible_fields.join(', ') || '无'}</dd></div>
              <div><dt>删除字段</dt><dd>{run.omitted_fields.join(', ') || '无'}</dd></div>
            </dl>
            <div className="handoff-prompt-heading"><h3>发给新 Codex 对话的 Prompt</h3><button className="btn btn-secondary" onClick={copyPrompt}>{copied ? '已复制' : '复制 Prompt'}</button></div>
            <textarea className="handoff-prompt" value={runPrompt.prompt} readOnly />
          </section>

          <section className="handoff-lab-band">
            <h2>提交本轮 Attempt</h2>
            <div className="handoff-attempt-grid">
              <label>对话 ID<input value={conversationId} onChange={(event) => setConversationId(event.target.value)} /></label>
              {Object.entries(tokens).map(([key, value]) => <label key={key}>{key}<input type="number" min="0" value={value} onChange={(event) => setTokens((current) => ({ ...current, [key]: event.target.value }))} /></label>)}
            </div>
            <label className="handoff-wide-field">Agent 最终输出（用于泄漏审计）<textarea value={agentOutput} onChange={(event) => setAgentOutput(event.target.value)} /></label>
            <label className="handoff-wide-field">备注<input value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
            <button className="btn btn-primary" onClick={submitAttempt} disabled={busy || run.status === 'resolved' || run.status === 'failed'}>运行隐藏评测并提交</button>
          </section>

          <section className="handoff-lab-band">
            <h2>运行结果</h2>
            <div className="handoff-metrics-row">
              <div><strong>{run.metrics.interaction_rounds}</strong><span>交互轮数</span></div>
              <div><strong>{run.metrics.rework_count}</strong><span>返工次数</span></div>
              <div><strong>{run.metrics.token_total}</strong><span>Token</span></div>
              <div><strong>{run.metrics.human_intervention_count}</strong><span>人工干预</span></div>
            </div>
            {latestAttempt && <div className="handoff-evaluation"><p>公开测试：{latestAttempt.evaluation.public.passed}/{latestAttempt.evaluation.public.total}</p><p>隐藏测试：{latestAttempt.evaluation.hidden.passed}/{latestAttempt.evaluation.hidden.total}</p><p>变更文件：{latestAttempt.evaluation.changed_files.join(', ') || '无'}</p>{latestAttempt.evaluation.hidden.failed_test_ids.length > 0 && <p>失败探针：{latestAttempt.evaluation.hidden.failed_test_ids.join(', ')}</p>}</div>}
            {run.repair_prompt && <label className="handoff-wide-field">发回同一对话的修复 Prompt<textarea value={run.repair_prompt} readOnly /></label>}
            {run.contaminated && <div className="error-message">检测到被删除字段的审计标记，本运行已污染。</div>}
          </section>
        </>
      )}
    </div>
  );
}
