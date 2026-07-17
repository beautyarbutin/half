# Reservation-v3 校准实验预注册

## 1. 实验定位

`reservation-v3` 是定向的实验管线校准任务，不用于单独证明任一 handoff 字段在一般软件任务中普遍重要。本轮冻结任务代码、完整 handoff、公开测试、隐藏测试、修复信号和最大尝试次数，只验证信息隔离、行为采集和预期机制是否能够被测量。

## 2. 冻结规则

每个 run 创建时记录以下 SHA-256：

- `manifest.json`
- `canonical_handoff.json`
- `canaries.json`
- 隐藏测试目录
- 初始 fixture 目录
- 实际发送 Prompt

提交 attempt 前重新计算输入哈希。任一输入发生变化时拒绝评测，该 run 不进入统计。

## 3. 预注册假设

### H1：unfinished_items 与最终正确性

相对于 `A_full`，`E_no_unfinished_items` 的最终隐藏测试通过率和三轮内任务成功率更低。

主要指标：

- 最终隐藏测试通过率
- 三轮内是否完成

辅助指标：

- 首轮成功率
- 返工次数
- 总 Token

### H2：verification 与执行效率

相对于 `A_full`，`D_no_verification` 的首轮成功率更低，总 Token 和返工次数更高。

主要指标：

- 首轮成功率
- 总 Token
- 返工次数

辅助指标：

- 测试执行次数
- 重复搜索次数
- 接口猜测次数

### H3：无 handoff 与仓库重新理解成本

相对于 `A_full`，`H_no_handoff` 的前置探索事件、唯一读取文件数、修改文件数和总 Token 更高。H3 为描述性校准假设，不作为单字段普遍重要性的正式推断。

## 4. 实验组和重复

本轮仅运行：

- `A_full`
- `D_no_verification`
- `E_no_unfinished_items`
- `H_no_handoff`

每组运行 2 次，共 8 个 run。执行顺序在运行前随机化并记录。每个 run 使用新的 Codex 对话、相同模型和推理强度、全新工作区，最多 3 个 attempt。

## 5. 泄漏审计门

每轮必须归档实际 Prompt、修复 Prompt、Agent 输出和完整工具调用 Trace。审计状态：

- `passed`：Trace 完整且被删除字段 canary、区分性长文本均为零命中。
- `failed`：检测到任一被删除字段证据。
- `unknown`：Trace 缺失或不完整。

只有 `passed` 的 run 进入主要结果表。`failed` 和 `unknown` 只进入审计附表。

## 6. Trace 事件操作化定义

| 事件 | 定义 |
|---|---|
| 读文件 | Trace 中的文件读取工具或等价命令 |
| 搜索 | `rg`、`Select-String`、`grep` 等搜索调用 |
| 重复搜索 | 同一标准化搜索命令在同一 run 再次出现 |
| 跑测试 | `pytest`、`npm test` 等测试命令 |
| 编辑 | `apply_patch` 或等价写文件操作 |
| 猜接口 | 前轮有失败探针后，再次编辑前轮已修改的契约文件 |
| 无效编辑 | 发生编辑且隐藏测试通过数没有高于前一轮 |
| 回滚 | `git restore`、`git checkout --`、`git revert/reset` 等 |
| 前置探索 | 首次编辑前的读文件与搜索事件 |

事件表必须保留 Trace 行号、工具名和脱敏摘要，保证计数可复核。

## 7. 人工干预

复制初始 Prompt、复制系统生成的修复 Prompt、提交已有输出属于机械操作，不计人工干预。任何额外解释、提示、纠错或方向建议均记录为人工干预，并记录耗时。

## 8. 停止规则

每个 run 成功时停止；否则最多运行 3 个 attempt。达到上限仍失败时，返工次数记为右截断值 2，不解释为任务只需要两次返工。

## 9. 转入自然任务的门槛

完成 8 个校准 run 后，只有满足以下条件才进入自然任务：

- 所有 run 都产生可读取 Trace；
- 审计脚本能稳定输出 `passed/failed/unknown`；
- 缺失 Trace 不会被标记为通过；
- 事件计数能够回溯到具体 Trace；
- 所有冻结输入哈希保持不变。
