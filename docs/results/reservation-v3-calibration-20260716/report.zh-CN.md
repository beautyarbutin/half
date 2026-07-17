# Reservation-v3 校准实验结果

## 1. 实验定位

本报告对应 cohort `reservation-v3-calibration-20260716`，包含预注册的 8 个 run。`reservation-v3` 是定向的实验管线校准任务，用于验证信息隔离、隐藏评测、Trace 事件统计和指标采集，不单独证明任一 handoff 字段在一般软件任务中普遍重要。

## 2. 有效性门

- 纳入分析：8/8 run。
- Trace 完整：8/8 run。
- 泄漏审计通过：8/8 run。
- 被删除字段命中：0。
- 输入完整性哈希验证：8/8 run。
- 人工干预：0。

因此，本 cohort 满足预注册的校准有效性门。

## 3. 主要结果

“最终成功”定义为最多三轮内隐藏测试全部通过；“首轮成功”为第一次 Attempt 即全部通过；测试通过率使用固定隐藏测试。

| 组别 | 最终成功率 | 首轮成功率 | 隐藏测试 | 平均 Token | 相对 A | 平均交互轮数 | 平均返工 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A 完整 | 100% | 100% | 20/20 | 282,514 | 1.00x | 1 | 0 |
| D 无 verification | 100% | 0% | 20/20 | 689,344 | 2.44x | 2.5 | 1.5 |
| E 无 unfinished_items | 0% | 0% | 18/20 | 827,010 | 2.93x | 3 | 2 |
| H 无 handoff | 0% | 0% | 17/20 | 1,019,314 | 3.61x | 3 | 2 |

## 4. Trace 行为结果

| 组别 | 读文件 | 唯一文件 | 搜索 | 测试 | 编辑 | 接口猜测 | 无效编辑轮 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A 完整 | 21 | 20 | 1.5 | 2 | 3 | 0 | 0 |
| D 无 verification | 29 | 23 | 5 | 4.5 | 7.5 | 4 | 0.5 |
| E 无 unfinished_items | 32 | 24.5 | 3.5 | 4.5 | 9 | 4 | 2 |
| H 无 handoff | 37 | 27 | 5.5 | 9.5 | 7 | 5 | 1.5 |

- A 组两次均首轮成功，且探索、测试和编辑成本最低，表现为直接接续前序工作。
- D 组最终均成功，但首轮均失败；Token、搜索、测试、编辑和接口猜测增加，缺少 `verification` 主要造成确认成本和返工。
- E 组两次在三轮后仍遗漏审计发布，最终均为 9/10；其编辑和无效编辑最多，缺少 `unfinished_items` 影响最终正确性。
- H 组两次均未在三轮内完成，读取和测试最多；相同三轮上限下，Token 仍高于 E，体现重新理解仓库和扩大上下文的额外成本。

## 5. 预注册假设

- **H1 unfinished_items -> final correctness**: `supported`. E final success 0/2 vs A 2/2; hidden tests 18/20 vs 20/20。
- **H2 verification -> efficiency**: `supported`. D first-attempt success 0/2 vs A 2/2; 2.44x tokens; 1.5 vs 0 mean reworks。
- **H3 no handoff -> repository relearning cost**: `supported_descriptively`. H reads 27 vs 20 unique files, runs 9.5 vs 2 tests, and uses 3.61x tokens。

## 6. 结论边界

本轮每组仅 2 次，结果只作描述性校准，不进行显著性检验。任务、字段与隐藏测试仍有定向绑定，因此不能把结果推广为字段的一般因果效应。下一阶段应在非定向自然任务上重复实验，并预先冻结任务、完整 handoff、模型、Prompt、评测器和分析规则。

## 7. 可复现文件

- `runs.csv`: 逐 run 结果与全部 Trace 计数。
- `group_summary.csv`: 分组聚合指标。
- `trace_events.csv`: Trace 事件均值。
- `leakage_audit.csv`: 每个 run 的隔离审计结果。
- `results.json`: cohort、逐 run、分组和假设的结构化结果。
