# Reservation-v3 Handoff 消融实验任务说明

> 本文档供实验设计者、评测者和论文撰写使用，不得提供给参与实验的后续 Agent。Agent 只能看到 HALF 为当前实验组生成的过滤后 Prompt 和独立代码工作区。

## 1. 实验目的

在固定后续开发任务、固定代码基线、固定模型的条件下，仅改变后续 Agent 可见的 handoff 字段，观察不同字段对以下结果的影响：

- 后续任务正确率；
- 公开测试通过率；
- 最终任务成功率；
- Token 消耗；
- 交互轮数和返工次数；
- 人工干预成本；
- 修改范围以及是否破坏前序成果。

本实验研究的是 handoff 信息的边际价值，不比较不同模型，也不比较不同代码任务。

## 2. 固定实验条件

| 项目 | 固定设置 |
|---|---|
| 实验 ID | `reservation-v3` |
| 目标代码仓库 | `handoff-fixture-reservation` |
| 代码基线 | `baseline/task-001-complete` |
| 后续 Agent | Codex |
| 模型 | `gpt-5.5` |
| 最大提交轮数 | 3 |
| 每组初始对话 | 新建独立 Codex 对话 |
| 返工对话 | 保持在该组同一 Codex 对话中 |
| 工作区 | 每组、每次运行创建独立副本 |
| 公开测试 | 工作区内 `tests/` |
| 隐藏测试 | HALF 私有实验目录，Agent 不可访问 |

每组必须使用相同代码基线、相同后续任务和相同模型。唯一自变量是后续 Agent 能看到的 handoff 字段集合。

## 3. 系统背景

目标系统是一个简化但完整的库存预约服务。客户提交订单行后，系统根据不同仓库的库存完成分配，生成预约记录，并返回 API 响应。

系统包含以下主要模块：

- `allocation/`：库存分配算法和分配策略；
- `reservation/`：预约服务、幂等端口和事务端口；
- `repositories/`：内存库存仓储、预约仓储和 Unit of Work；
- `api/schemas.py`：请求解析；
- `api/serializer.py`：预约对象序列化；
- `api/reservation.py`：后续 API 集成点；
- `events/audit.py`：后续审计事件集成点；
- `legacy/`：旧实现或兼容路径，不应作为当前主实现使用。

## 4. 前序任务 TASK-001 状态

实验假设前序 Agent 已完成以下能力：

- 库存分配算法；
- 多仓库库存拆分；
- 重复 SKU 聚合；
- `ReservationService`；
- 内存仓储和 Unit of Work；
- 请求 schema；
- API serializer；
- 幂等存储；
- 分配与服务层单元测试。

前序阶段修改或确认过的主要文件为：

```text
src/reservation_fixture/allocation/engine.py
src/reservation_fixture/reservation/service.py
src/reservation_fixture/api/schemas.py
src/reservation_fixture/api/serializer.py
tests/test_allocation.py
tests/test_service.py
```

以下两个后续集成点仍为未完成状态：

```text
src/reservation_fixture/api/reservation.py::reserve_order
src/reservation_fixture/events/audit.py::record_reservation_audit
```

## 5. 后续任务 TASK-002

后续 Agent 必须完成库存预约 API 集成，实现：

```python
reserve_order(
    payload,
    *,
    uow_factory,
    idempotency,
    publisher,
) -> dict[str, object]
```

### 5.1 请求处理

- 使用现有 `api.schemas.parse_request` 解析请求；
- 支持旧请求字段 `warehouse` 作为 `preferred_warehouse` 的兼容别名；
- 兼容转换应局限在 API 边界；
- 不得修改调用者传入的原始 `payload`；
- 重复 SKU 行应沿用前序实现进行聚合。

### 5.2 预约与事务

- 使用现有 `ReservationService.reserve` 完成预约；
- 通过 Unit of Work 管理库存和预约写入；
- 成功时提交事务；
- 任一失败必须回滚库存和预约写入；
- 不得重新实现第二套库存分配算法。

### 5.3 幂等行为

- 首次出现的 `idempotency_key` 正常执行预约；
- 重复 key 返回首次请求生成的原始响应；
- 重复请求不得再次扣减库存；
- 重复请求不得再次发布审计事件；
- 事务提交失败时不得保存幂等结果。

### 5.4 审计事件

事务成功提交后调用 `record_reservation_audit`，发布且仅发布一个事件：

```text
事件名：reservation.created
```

事件 payload 必须且只能包含：

```text
reservation_id
order_id
status
total
```

其中 `total` 使用与 API 响应一致的两位小数字符串；审计 payload 不得包含 `allocations`。

### 5.5 API 响应

使用现有 `api.serializer.reservation_to_dict` 返回普通字典。响应字段为：

```text
reservation_id
order_id
status
total
allocations
```

## 6. 最小 Handoff Schema

实验使用固定的六字段 schema：

```json
{
  "goal": "后续阶段目标和交付契约",
  "changed_files": ["前序修改过的仓库相对路径"],
  "verification": "前序已执行的验证及其结论",
  "unfinished_items": "仍未完成的工作和必要契约",
  "risks": "风险、约束和禁止行为",
  "next_steps": "建议的后续实现顺序"
}
```

本任务中各字段承载的信息为：

| 字段 | 主要信息 |
|---|---|
| `goal` | 完成 `reserve_order`，返回现有 serializer 定义的 API 契约 |
| `changed_files` | 前序已修改文件和已完成模块边界 |
| `verification` | `warehouse` 别名及重复 SKU 聚合已被前序验证 |
| `unfinished_items` | API、audit 尚未集成，以及精确 audit 事件契约 |
| `risks` | 幂等、回滚、输入不可变、提交后发布、Decimal 内部表示 |
| `next_steps` | 组合 parser、service、audit、serializer，避免 legacy 实现 |

## 7. 消融组

| 组别 | 可见 handoff | 删除字段 |
|---|---|---|
| `A_full` | 六字段全部可见 | 无 |
| `B_no_goal` | 除 `goal` 外全部可见 | `goal` |
| `C_no_changed_files` | 除 `changed_files` 外全部可见 | `changed_files` |
| `D_no_verification` | 除 `verification` 外全部可见 | `verification` |
| `E_no_unfinished_items` | 除 `unfinished_items` 外全部可见 | `unfinished_items` |
| `F_no_risks` | 除 `risks` 外全部可见 | `risks` |
| `G_no_next_steps` | 除 `next_steps` 外全部可见 | `next_steps` |
| `H_no_handoff` | 无 handoff | 全部字段 |

## 8. 隐藏评测设计

HALF 使用 10 个隐藏测试验证后续实现。测试只在 Agent 提交后由 HALF 执行。

| 字段 | Probe 数量 | 检查内容 |
|---|---:|---|
| `goal` | 1 | API 成功响应契约 |
| `changed_files` | 2 | 使用当前前序模块；不重写完成的核心模块 |
| `verification` | 1 | 保留 `warehouse` 别名和重复 SKU 行为 |
| `unfinished_items` | 1 | 精确审计事件名称、payload 边界和金额序列化 |
| `risks` | 4 | 幂等无二次副作用、失败回滚、输入不可变、提交后发布 |
| `next_steps` | 1 | 正确组合前序扩展点，不调用 legacy 实现 |

隐藏测试总数为 10。所有隐藏测试和公开测试均通过时，本轮任务才判定为完成。

## 9. 执行流程

```text
选择实验组
→ HALF 从固定 baseline 创建独立 workspace
→ HALF 从私有完整 handoff 中删除该组指定字段
→ 生成只含可见字段的 Prompt
→ 在新的 Codex 对话中执行后续任务
→ 将 Agent 输出和 Token 数据提交给 HALF
→ HALF 运行公开测试和隐藏测试
→ 若失败，生成不泄漏具体断言的修复方向
→ 在同一对话中返工
→ 成功或达到 3 次提交上限后结束
```

Agent 不得访问：

- 完整 canonical handoff；
- 隐藏测试；
- 其他实验组工作区；
- HALF 私有实验目录；
- 协作仓库或 Git 历史中可能泄漏的完整信息。

## 10. 指标定义

| 指标 | 定义 |
|---|---|
| 隐藏准确率 | 隐藏测试通过数 / 10 |
| 公开测试通过率 | 当前工作区公开测试通过数 / 当前公开测试总数 |
| 最终任务成功 | 在最大 3 轮内公开和隐藏测试全部通过 |
| 首轮成功 | 第一次提交即满足最终任务成功条件 |
| 交互轮数 | 向 HALF 提交评测的次数 |
| 返工次数 | `交互轮数 - 1`；失败并达到上限时为截断值 |
| Token 消耗 | 该实验组同一运行中所有 Agent 轮次 Token 总和 |
| 相对 Token | `(实验组 Token - A_full Token) / A_full Token` |
| 人工干预 | 实验协议之外的人工补充、修改或解释次数与耗时 |
| 修改范围 | 最终修改文件数及整个运行涉及的不同文件数 |
| 前序破坏 | 是否修改禁止修改的前序核心模块 |
| 污染 | Agent 输出是否出现被删除字段的私有审计标记 |

正常复制初始 Prompt、复制 HALF 自动生成的修复 Prompt，不计为人工干预。网络中断和工具故障应记录为基础设施重试。

## 11. 验收标准

单次运行成功必须同时满足：

1. 公开测试全部通过；
2. 10 个隐藏测试全部通过；
3. 未达到最大尝试次数前完成；
4. 未发生实验污染；
5. 未修改禁止修改的前序核心模块。

## 12. 解释边界

本实验是受控 pilot，而不是对所有软件任务的普遍结论。公开测试数量会因 Agent 自行增加测试而变化，因此不同组之间主要比较通过率，而不直接比较公开测试数量。

当前任务中，`unfinished_items` 包含代码中无法唯一推断的精确 audit 契约，`verification` 包含已验证的兼容行为；其他字段的部分信息可能由 Agent 从代码结构或常规工程经验恢复。正式结论需要每组多次独立重复，并报告均值、方差、成功率和置信区间。
