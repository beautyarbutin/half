import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';

export default function LoginPage() {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await api.post<{ token: string }>('/api/auth/login', {
        username: 'admin',
        password,
      });
      localStorage.setItem('token', result.token);
      navigate('/projects');
    } catch {
      setError('登录失败，请检查密码是否正确。');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <h1>HALF</h1>
        <p className="login-subtitle">Human-AI Loop Framework</p>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="password" title="请输入系统登录密码。默认账号为 admin。">登录密码</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入登录密码"
              title="输入系统登录密码后即可进入项目首页。"
              autoFocus
            />
          </div>
          {error && <div className="error-message">{error}</div>}
          <button type="submit" className="btn btn-primary btn-full" disabled={loading} title="提交密码并登录系统">
            {loading ? '登录中...' : '登录'}
          </button>
        </form>
      </div>
    </div>
  );
}
