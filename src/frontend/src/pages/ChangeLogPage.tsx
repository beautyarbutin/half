import React from 'react';

const updatedAt = '2026-04-03 22:35 +08:00';

export default function ChangeLogPage() {
  return (
    <div className="page">
      <div className="page-header">
        <h1>修改记录</h1>
      </div>

      <div className="change-log-card">
        <div className="change-log-meta">
          <span>修改模型：gpt-5.4</span>
          <span>修改时间：{updatedAt}</span>
        </div>

        <div className="change-log-section">
          <h3>本次更新</h3>
          <ul className="change-log-list">
            <li>左侧导航新增“修改记录”入口，集中记录本轮调整内容。</li>
            <li>Agents 页面优化新增表单：Slug 改为系统自动生成，不再展示给用户。</li>
            <li>Agent Type 改为预设下拉，并支持手工补充未覆盖的类型。</li>
            <li>Model Name 根据 Agent Type 联动提供常见选项，同时支持手工输入。</li>
            <li>机器标识和订阅到期时间保留为选填，降低新增 Agent 的填写负担。</li>
            <li>修复创建 Agent 时订阅到期时间未保存的问题。</li>
            <li>Agents 页面新增删除功能；已关联任务或项目的 Agent 会阻止删除并提示原因。</li>
            <li>Agents 页面新增“短期重置间隔（小时）”“长期重置间隔（天）”两个可选字段，创建和编辑时都可填写。</li>
            <li>如果设置了重置时间和对应间隔，系统会在到期后自动顺延到下一轮时间。</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
