# sqlite-utils positional iterator 接续任务说明

## 仓库

- 实验仓库：`beautyarbutin/handoff-natural-sqlite-utils`
- 固定 TASK-001 tag：`natural-task-001`
- HALF 实验 ID：`sqlite-utils-list-iterator-v1`

## 固定前序状态

仓库包含真实 `sqlite-utils` 项目代码和完整公开回归测试。TASK-001 已扩展内部 SQL query
构造和 chunk 写入管线，使其能在显式 positional 模式下处理 sequence rows，并验证了：

- 短行补 `NULL`、长行截断；
- JSON 值序列化；
- extracts；
- 原有 dictionary 模式回归。

TASK-001 没有完成公开 API 接入。

## 固定后续任务

后续 Agent 需要完成 `Table.insert_all()` 和 `Table.upsert_all()` 的公开 positional iterator
支持：迭代器首个 sequence 是列名，后续 sequence 是数据行；同时保持现有 dictionary-record
行为。

## 为什么选择该任务

1. 来源于真实开源项目需求，不是为 handoff 字段编造的功能。
2. 项目约 3 万行、公开测试超过 1000 个，Agent 需要在真实上下文中定位。
3. 前序内部管线与后续公开入口存在自然接续边界。
4. 任务包含 iterator peek、批处理、类型推断、upsert、主键、extracts 和兼容性边界。
5. 完整公开回归约 16 秒，适合重复实验，不会因测试耗时失控。

## 已知限制

- 前序和后续主要修改同一个核心源文件，因此 `changed_files` 的定位价值可能偏弱。
- 公开需求本身描述了首行表头语义，因此部分信息可从任务描述恢复。
- 该任务用于自然任务复现，不替代跨仓库、多任务的外部有效性验证。
