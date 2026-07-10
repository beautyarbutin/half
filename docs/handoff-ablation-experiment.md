# Handoff 字段消融实验

本文档描述 HALF 当前支持的轻量 handoff 字段消融能力。该能力用于固定同一个后续任务，对比不同 handoff 字段组合或上下文策略对 Agent 表现的影响。

## 最小 handoff schema

前序任务应在自己的任务目录写入 `handoff.json`：

```json
{
  "goal": "本阶段目标",
  "changed_files": ["修改过的文件"],
  "verification": "已经跑过的测试和结果",
  "unfinished_items": "未完成事项",
  "risks": "风险和约束",
  "next_steps": "建议下一步"
}
```

字段集合固定为：

- `goal`
- `changed_files`
- `verification`
- `unfinished_items`
- `risks`
- `next_steps`

## 消融组

| arm | 注入给后续 Agent 的内容 | 目的 |
|---|---|---|
| `A_full` | 全部 6 个字段 | 基线 |
| `B_no_verification` | 去掉 `verification` | 看测试信息是否关键 |
| `C_no_unfinished_items` | 去掉 `unfinished_items` | 看是否更容易漏任务 |
| `D_no_risks` | 去掉 `risks` | 看是否更容易误改、破坏既有逻辑 |
| `E_summary_only` | 不给结构化字段，只给自然语言摘要 | 比较结构化 handoff 是否更好 |
| `F_full_context` | 给前序 `handoff.json` 与 `result.json` 原文 | 比较全文上下文是否浪费 token 或干扰判断 |

## HALF 行为

在任务详情页选择“Handoff 实验组”后，HALF 生成任务 prompt 时会：

1. 读取前序任务目录中的 `handoff.json`。
2. 按所选 arm 过滤字段或转换格式。
3. 将处理后的 handoff 注入后续任务 prompt。
4. 在派发/重新派发事件中记录 `Handoff arm: <arm_id>`。

不选择实验组时，HALF 沿用普通任务 prompt，不读取前序 `handoff.json`。

## 协作仓库路径

假设项目协作目录是：

```text
outputs/handoff-exp/A_full/run01
```

前序任务应写：

```text
outputs/handoff-exp/A_full/run01/TASK-001/handoff.json
outputs/handoff-exp/A_full/run01/TASK-001/result.json
```

后续任务 prompt 会读取上述 `handoff.json` 并按 arm 注入。

