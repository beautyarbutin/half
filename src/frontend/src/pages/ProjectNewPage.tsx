import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { Agent, Project } from '../types';

export default function ProjectNewPage() {
  const { id } = useParams<{ id: string }>();
  const isEditMode = Boolean(id);
  const [name, setName] = useState('');
  const [goal, setGoal] = useState('');
  const [gitRepoUrl, setGitRepoUrl] = useState('');
  const [collaborationDir, setCollaborationDir] = useState('');
  const [selectedAgentIds, setSelectedAgentIds] = useState<number[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const hasAgents = agents.length > 0;
  const canSubmit = hasAgents && selectedAgentIds.length > 0 && name.trim() && goal.trim() && !loading;
  const pageTitle = isEditMode ? '编辑项目' : '新建项目';

  useEffect(() => {
    async function fetchData() {
      try {
        const [agentList, project] = await Promise.all([
          api.get<Agent[]>('/api/agents'),
          isEditMode ? api.get<Project>(`/api/projects/${id}`) : Promise.resolve(null),
        ]);
        setAgents(agentList);
        if (project) {
          setName(project.name || '');
          setGoal(project.goal || '');
          setGitRepoUrl(project.git_repo_url || '');
          setCollaborationDir(project.collaboration_dir || '');
          setSelectedAgentIds(project.agent_ids || []);
        }
      } catch (err) {
        setError(`加载项目数据失败：${err}`);
      } finally {
        setInitializing(false);
      }
    }
    fetchData();
  }, [id, isEditMode]);

  const sortedAgents = useMemo(() => [...agents].sort((a, b) => a.name.localeCompare(b.name)), [agents]);

  function toggleAgent(agentId: number) {
    setSelectedAgentIds((prev) =>
      prev.includes(agentId)
        ? prev.filter((currentId) => currentId !== agentId)
        : [...prev, agentId]
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    if (!hasAgents) {
      setError('当前系统还没有 Agent，请先到 Agents 页面新增。');
      return;
    }
    if (selectedAgentIds.length === 0) {
      setError('请至少选择 1 个 Agent 后再继续。');
      return;
    }

    setLoading(true);
    try {
      const payload = {
        name,
        goal,
        git_repo_url: gitRepoUrl,
        collaboration_dir: collaborationDir,
        agent_ids: selectedAgentIds,
      };
      const project = isEditMode
        ? await api.put<Project>(`/api/projects/${id}`, payload)
        : await api.post<Project>('/api/projects', payload);
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setError(`${isEditMode ? '更新项目' : '创建项目'}失败：${err}`);
    } finally {
      setLoading(false);
    }
  }

  if (initializing) return <div className="page-loading">正在加载项目配置...</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>{pageTitle}</h1>
      </div>

      {!hasAgents && (
        <div className="empty-state compact-empty-state">
          <p>当前系统还没有注册 Agent，请先到 Agents 页面新增，再回来创建项目。</p>
          <Link to="/agents" className="btn btn-primary" title="前往 Agents 页面新增可用 Agent">
            前往 Agents 页面
          </Link>
        </div>
      )}

      <form className="form" onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="name" title="填写一个清晰的项目名称，便于在项目列表中快速识别。">项目名称</label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="例如：企业知识库助手"
            title="建议使用简短、明确、便于区分的项目名称。"
          />
        </div>

        <div className="form-group">
          <label htmlFor="goal" title="说明项目要解决的问题、目标结果和交付内容。">项目目标</label>
          <textarea
            id="goal"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            required
            rows={4}
            placeholder="请描述项目要完成什么、交付什么，以及验收标准。"
            title="这里的描述会直接影响后续 Plan 和任务拆解质量，请尽量具体。"
          />
        </div>

        <div className="form-group">
          <label htmlFor="repo" title="如项目关联代码仓库，请填写 Git 仓库地址；没有可暂时留空。">Git 仓库地址</label>
          <input
            id="repo"
            type="text"
            value={gitRepoUrl}
            onChange={(e) => setGitRepoUrl(e.target.value)}
            placeholder="例如：git@github.com:org/repo.git"
            title="建议填写可访问的仓库地址，便于后续任务执行时引用代码上下文。"
          />
        </div>

        <div className="form-group">
          <label htmlFor="collaboration-dir" title="填写仓库内用于多 Agent 协作的目录，例如存放任务码、过程文件或中间结果的目录。">协作目录</label>
          <input
            id="collaboration-dir"
            type="text"
            value={collaborationDir}
            onChange={(e) => setCollaborationDir(e.target.value)}
            placeholder="例如：tasks/shared（留空则使用仓库根目录）"
            title="请填写 Git 仓库中的相对目录路径，供多 Agent 协作时统一存放任务文件。"
          />
        </div>

        <div className="form-group">
          <label title="选择可以参与该项目执行的 Agent。创建项目时必须至少选择 1 个。">Agents</label>
          <div className="agent-select-grid">
            {sortedAgents.map((agent) => (
              <label
                key={agent.id}
                className="agent-option"
                title={`勾选后，${agent.name} 将可以参与此项目的任务执行。`}
              >
                <input
                  type="checkbox"
                  checked={selectedAgentIds.includes(agent.id)}
                  onChange={() => toggleAgent(agent.id)}
                  title={`选择 ${agent.name} 作为项目可用 Agent`}
                />
                <span className="agent-option-name">{agent.name}</span>
                <span className="agent-option-type">{agent.agent_type}</span>
              </label>
            ))}
          </div>
          {hasAgents && selectedAgentIds.length === 0 && (
            <div className="helper-text helper-text-error">请至少选择 1 个 Agent。</div>
          )}
        </div>

        {error && <div className="error-message">{error}</div>}

        <div className="form-actions">
          <button type="button" className="btn btn-ghost" onClick={() => navigate(-1)} title="返回上一页，不保存当前输入内容">
            取消
          </button>
          <button type="submit" className="btn btn-primary" disabled={!canSubmit} title={hasAgents ? '保存项目信息并进入项目详情页' : '请先新增 Agent'}>
            {loading ? (isEditMode ? '更新中...' : '创建中...') : (isEditMode ? '更新项目' : '创建项目')}
          </button>
        </div>
      </form>
    </div>
  );
}
