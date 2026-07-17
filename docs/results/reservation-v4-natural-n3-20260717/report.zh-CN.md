# Reservation-v4 Natural 三轮实验结果

## 1. 实验范围

本报告对应 cohort `reservation-v4-natural-n3-20260717`。实验使用自然拆分的“取消预约并恢复库存”任务，
比较 `A_full`、`D_no_verification`、`E_no_unfinished_items` 和 `H_no_handoff`
四组，每组 3 个有效 run，共 12 个有效 run。每个 run 使用新 Codex 对话和独立工作区。

## 2. 有效性门

- 纳入分析：12/12 个 cohort 指定 run。
- Trace 完整：通过。
- 泄漏审计：12/12 passed，删字段内容零命中。
- 输入完整性哈希：12/12 通过。
- 人工干预：0 次。

## 3. 主要结果

| 组别 | n | 首轮成功率 | 最终成功率 | 隐藏测试 | Token 中位数 | Token 均值 | Token 标准差 | 中位数相对 A | 平均返工 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A 完整 handoff | 3 | 100% | 100% | 30/30 | 216,962 | 305,978 | 185,531 | 1.00x | 0 |
| D 删除 verification | 3 | 100% | 100% | 30/30 | 258,100 | 264,418 | 16,833 | 1.19x | 0 |
| E 删除 unfinished_items | 3 | 100% | 100% | 30/30 | 209,129 | 227,373 | 64,022 | 0.96x | 0 |
| H 无 handoff | 3 | 100% | 100% | 30/30 | 306,984 | 367,144 | 123,450 | 1.41x | 0 |

四组 12 个有效 run 均在首轮通过全部隐藏测试，因此本任务未观察到正确性、返工或人工干预差异。
Token 的组内波动明显，尤其是 A 和 H；因此主要报告中位数，同时保留均值、标准差和范围。
两项关键字段假设及固定条件在 pilot 前预注册；第 2、3 次重复是在观察 pilot 后追加，
因此本报告明确区分“预注册假设”和“后续扩展样本”。

## 4. Trace 行为

| 组别 | 读文件 | 唯一文件 | 搜索 | 重复搜索 | 测试 | 编辑 | 接口猜测 | 无效编辑轮 | 回滚 | 变更文件 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A 完整 handoff | 17 | 17.3 | 2 | 0 | 2.7 | 2.3 | 0 | 0 | 0 | 4.3 |
| D 删除 verification | 20.3 | 20.7 | 2 | 0 | 2.3 | 2.3 | 0 | 0 | 0 | 4.7 |
| E 删除 unfinished_items | 19 | 19 | 2.7 | 0 | 2 | 1.7 | 0 | 0 | 0 | 4 |
| H 无 handoff | 28.7 | 26.3 | 3 | 0.3 | 2 | 2 | 0 | 0 | 0 | 5.3 |

H 的文件读取、搜索、变更范围和 Token 中位数均高于 A，说明没有 handoff 时，
Agent 更倾向于重新理解仓库。D 的 Token 中位数高于 A，但测试和返工并未增加；
E 与 A 的 Token 中位数接近，未形成稳定成本差异。

## 5. 预注册假设

- **H1 `unfinished_items -> 最终正确性`：未支持。** E 的首轮与最终成功率均为 100%，隐藏测试为 30/30，与 A 没有正确性差异。
- **H2 `verification -> Token、返工与首轮成功率`：仅有 Token 方向性证据。** D 的 Token 中位数比 A 高 19.0%，但首轮成功率、最终成功率和返工次数与 A 相同。
- **H3 `无 handoff -> 仓库重新理解成本`：描述性支持。** H 平均读取 28.7 次文件，A 为 17 次；H 的 Token 中位数为 A 的 1.41 倍。

## 6. 排除记录

- `20260717T063529Z-f2105644`：Protocol violation: the agent edited workspace 20260717T040138Z-11223fcf instead of the assigned 20260717T063529Z-f2105644 workspace; the evaluated workspace received no code changes. 原始证据保留于 `D:\code\workspace\half-experiment-runs\reservation-v4-natural\A_full\20260717T063529Z-f2105644`。

排除依据在观察结果前由协议违规事实确定，不依据 Token 高低或测试成败选择样本。

## 7. 结论边界

每组只有 3 次运行，结果仍属于探索性证据，不进行显著性检验，也不宣称字段具有普遍因果效应。
pilot 使用固定随机种子安排顺序，后两轮按实际操作顺序记录但未重新随机化，
因此仍可能存在时间或执行顺序影响。
本轮较稳定的发现是：完整 handoff 没有改变最终正确性，但缺少全部 handoff 会增加仓库探索行为。
`verification` 对 Token 可能有影响，但需要更多重复或第二个自然任务验证；
`unfinished_items` 对最终正确性的预注册假设在本任务中未得到支持。

## 8. 可复现文件

- `runs.csv`：12 个有效 run 的结果、Token、Trace 和审计指标。
- `group_summary.csv`：每组均值、中位数、标准差和范围。
- `attempt_summary.csv`：逐 Attempt 的评测与事件计数。
- `failed_attempt_summary.csv`：仅保留失败 Attempt 的汇总。
- `attempt_event_timeline.csv`：逐工具调用的事件时间线。
- `failed_attempt_event_timeline.csv`：仅保留失败 Attempt 的时间线。
- `trace_events.csv`：分组 Trace 均值。
- `leakage_audit.csv`：逐 run 泄漏审计。
- `exclusions.csv`：排除样本、原因和证据位置。
- `results.json`：完整结构化结果。
