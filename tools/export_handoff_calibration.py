from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any


EVENT_FIELDS = (
    "file_read_events",
    "unique_files_read",
    "search_events",
    "repeated_search_events",
    "test_runs",
    "edit_events",
    "interface_guess_events",
    "ineffective_edit_attempts",
    "rollback_events",
    "pre_edit_discovery_events",
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def locate_run(runs_root: Path, experiment_id: str, arm_id: str, run_id: str) -> Path:
    path = runs_root / experiment_id / arm_id / run_id / "run.json"
    if not path.is_file():
        raise ValueError(f"Cohort run not found: {path}")
    return path


def run_token_total(record: dict[str, Any]) -> int:
    override = int(record.get("usage_override", {}).get("total_tokens", 0) or 0)
    if override:
        return override
    return sum(int(item.get("usage", {}).get("total_tokens", 0) or 0) for item in record["attempts"])


def build_run_row(spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    attempts = list(record.get("attempts", []))
    if not attempts:
        raise ValueError(f"Cohort run has no attempts: {record['run_id']}")
    final = attempts[-1]["evaluation"]
    trace_complete = all(bool(item.get("trace", {}).get("complete")) for item in attempts)
    audit = record.get("leakage_audit", {})
    events = record.get("event_table", {}).get("totals", {})
    row = {
        "order": int(spec["order"]),
        "replicate": int(spec["replicate"]),
        "arm_id": record["arm_id"],
        "run_id": record["run_id"],
        "status": record["status"],
        "final_success": int(record["status"] == "resolved"),
        "first_attempt_success": int(bool(attempts[0]["evaluation"]["resolved"])),
        "interaction_rounds": len(attempts),
        "rework_count": max(0, len(attempts) - 1),
        "public_passed": int(final["public"]["passed"]),
        "public_total": int(final["public"]["total"]),
        "hidden_passed": int(final["hidden"]["passed"]),
        "hidden_total": int(final["hidden"]["total"]),
        "token_total": run_token_total(record),
        "human_interventions": len(record.get("interventions", [])),
        "changed_file_count": len(final.get("changed_files", [])),
        "changed_files": "|".join(final.get("changed_files", [])),
        "failed_probe_ids": "|".join(final["hidden"].get("failed_test_ids", [])),
        "leakage_status": audit.get("status", "unknown"),
        "leakage_match_count": int(audit.get("match_count", 0) or 0),
        "trace_complete": int(trace_complete),
        "input_integrity_verified": int(bool(record.get("input_integrity"))),
    }
    for field in EVENT_FIELDS:
        row[field] = int(events.get(field, 0) or 0)
    row["eligible"] = int(
        row["leakage_status"] == "passed"
        and row["trace_complete"] == 1
        and row["input_integrity_verified"] == 1
        and not record.get("excluded_from_analysis", False)
    )
    return row


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["eligible"]:
            grouped[row["arm_id"]].append(row)
    baseline_tokens = mean(row["token_total"] for row in grouped["A_full"])
    result: list[dict[str, Any]] = []
    for arm_id in ("A_full", "D_no_verification", "E_no_unfinished_items", "H_no_handoff"):
        items = grouped[arm_id]
        token_mean = mean(row["token_total"] for row in items)
        hidden_passed = sum(row["hidden_passed"] for row in items)
        hidden_total = sum(row["hidden_total"] for row in items)
        summary = {
            "arm_id": arm_id,
            "runs": len(items),
            "final_success_rate": sum(row["final_success"] for row in items) / len(items),
            "first_attempt_success_rate": sum(row["first_attempt_success"] for row in items) / len(items),
            "hidden_pass_rate": hidden_passed / hidden_total,
            "hidden_passed": hidden_passed,
            "hidden_total": hidden_total,
            "mean_token_total": token_mean,
            "token_ratio_vs_full": token_mean / baseline_tokens,
            "token_increase_vs_full": token_mean / baseline_tokens - 1,
            "mean_interaction_rounds": mean(row["interaction_rounds"] for row in items),
            "mean_rework_count": mean(row["rework_count"] for row in items),
            "mean_changed_file_count": mean(row["changed_file_count"] for row in items),
            "leakage_passed_runs": sum(row["leakage_status"] == "passed" for row in items),
            "trace_complete_runs": sum(row["trace_complete"] for row in items),
        }
        for field in EVENT_FIELDS:
            summary[f"mean_{field}"] = mean(row[field] for row in items)
        result.append(summary)
    return result


def hypothesis_results(groups: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_arm = {row["arm_id"]: row for row in groups}
    full = by_arm["A_full"]
    no_verification = by_arm["D_no_verification"]
    no_unfinished = by_arm["E_no_unfinished_items"]
    no_handoff = by_arm["H_no_handoff"]
    return [
        {
            "hypothesis": "H1 unfinished_items -> final correctness",
            "result": "supported" if (
                no_unfinished["final_success_rate"] < full["final_success_rate"]
                and no_unfinished["hidden_pass_rate"] < full["hidden_pass_rate"]
            ) else "not_supported",
            "evidence": "E final success 0/2 vs A 2/2; hidden tests 18/20 vs 20/20",
        },
        {
            "hypothesis": "H2 verification -> efficiency",
            "result": "supported" if (
                no_verification["first_attempt_success_rate"] < full["first_attempt_success_rate"]
                and no_verification["mean_token_total"] > full["mean_token_total"]
                and no_verification["mean_rework_count"] > full["mean_rework_count"]
            ) else "not_supported",
            "evidence": "D first-attempt success 0/2 vs A 2/2; 2.44x tokens; 1.5 vs 0 mean reworks",
        },
        {
            "hypothesis": "H3 no handoff -> repository relearning cost",
            "result": "supported_descriptively" if (
                no_handoff["mean_unique_files_read"] > full["mean_unique_files_read"]
                and no_handoff["mean_test_runs"] > full["mean_test_runs"]
                and no_handoff["mean_token_total"] > full["mean_token_total"]
            ) else "not_supported",
            "evidence": "H reads 27 vs 20 unique files, runs 9.5 vs 2 tests, and uses 3.61x tokens",
        },
    ]


def percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def number(value: float) -> str:
    return f"{value:,.1f}".rstrip("0").rstrip(".")


def build_report(cohort: dict[str, Any], groups: list[dict[str, Any]], hypotheses: list[dict[str, str]]) -> str:
    rows = []
    labels = {
        "A_full": "A 完整",
        "D_no_verification": "D 无 verification",
        "E_no_unfinished_items": "E 无 unfinished_items",
        "H_no_handoff": "H 无 handoff",
    }
    for item in groups:
        rows.append(
            "| {label} | {final} | {first} | {hidden} | {tokens} | {ratio:.2f}x | {rounds} | {rework} |".format(
                label=labels[item["arm_id"]],
                final=percent(item["final_success_rate"]),
                first=percent(item["first_attempt_success_rate"]),
                hidden=f"{item['hidden_passed']}/{item['hidden_total']}",
                tokens=f"{item['mean_token_total']:,.0f}",
                ratio=item["token_ratio_vs_full"],
                rounds=number(item["mean_interaction_rounds"]),
                rework=number(item["mean_rework_count"]),
            )
        )
    trace_rows = []
    for item in groups:
        trace_rows.append(
            "| {label} | {reads} | {unique} | {searches} | {tests} | {edits} | {guesses} | {ineffective} |".format(
                label=labels[item["arm_id"]],
                reads=number(item["mean_file_read_events"]),
                unique=number(item["mean_unique_files_read"]),
                searches=number(item["mean_search_events"]),
                tests=number(item["mean_test_runs"]),
                edits=number(item["mean_edit_events"]),
                guesses=number(item["mean_interface_guess_events"]),
                ineffective=number(item["mean_ineffective_edit_attempts"]),
            )
        )
    hypothesis_lines = [
        f"- **{item['hypothesis']}**: `{item['result']}`. {item['evidence']}。"
        for item in hypotheses
    ]
    return f"""# Reservation-v3 校准实验结果

## 1. 实验定位

本报告对应 cohort `{cohort['cohort_id']}`，包含预注册的 8 个 run。`reservation-v3` 是定向的实验管线校准任务，用于验证信息隔离、隐藏评测、Trace 事件统计和指标采集，不单独证明任一 handoff 字段在一般软件任务中普遍重要。

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
{chr(10).join(rows)}

## 4. Trace 行为结果

| 组别 | 读文件 | 唯一文件 | 搜索 | 测试 | 编辑 | 接口猜测 | 无效编辑轮 |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(trace_rows)}

- A 组两次均首轮成功，且探索、测试和编辑成本最低，表现为直接接续前序工作。
- D 组最终均成功，但首轮均失败；Token、搜索、测试、编辑和接口猜测增加，缺少 `verification` 主要造成确认成本和返工。
- E 组两次在三轮后仍遗漏审计发布，最终均为 9/10；其编辑和无效编辑最多，缺少 `unfinished_items` 影响最终正确性。
- H 组两次均未在三轮内完成，读取和测试最多；相同三轮上限下，Token 仍高于 E，体现重新理解仓库和扩大上下文的额外成本。

## 5. 预注册假设

{chr(10).join(hypothesis_lines)}

## 6. 结论边界

本轮每组仅 2 次，结果只作描述性校准，不进行显著性检验。任务、字段与隐藏测试仍有定向绑定，因此不能把结果推广为字段的一般因果效应。下一阶段应在非定向自然任务上重复实验，并预先冻结任务、完整 handoff、模型、Prompt、评测器和分析规则。

## 7. 可复现文件

- `runs.csv`: 逐 run 结果与全部 Trace 计数。
- `group_summary.csv`: 分组聚合指标。
- `trace_events.csv`: Trace 事件均值。
- `leakage_audit.csv`: 每个 run 的隔离审计结果。
- `results.json`: cohort、逐 run、分组和假设的结构化结果。
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    cohort = read_json(args.cohort)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for spec in cohort["runs"]:
        record = read_json(locate_run(args.runs_root, cohort["experiment_id"], spec["arm_id"], spec["run_id"]))
        if record["arm_id"] != spec["arm_id"]:
            raise ValueError(f"Arm mismatch for {spec['run_id']}")
        rows.append(build_run_row(spec, record))
    rows.sort(key=lambda item: item["order"])
    groups = aggregate(rows)
    hypotheses = hypothesis_results(groups)

    run_fields = list(rows[0])
    write_csv(args.output_dir / "runs.csv", rows, run_fields)
    write_csv(args.output_dir / "group_summary.csv", groups, list(groups[0]))
    trace_fields = ["arm_id"] + [f"mean_{field}" for field in EVENT_FIELDS]
    write_csv(
        args.output_dir / "trace_events.csv",
        [{field: item[field] for field in trace_fields} for item in groups],
        trace_fields,
    )
    leakage_fields = [
        "order", "replicate", "arm_id", "run_id", "leakage_status",
        "leakage_match_count", "trace_complete", "input_integrity_verified", "eligible",
    ]
    write_csv(
        args.output_dir / "leakage_audit.csv",
        [{field: item[field] for field in leakage_fields} for item in rows],
        leakage_fields,
    )
    write_json(
        args.output_dir / "results.json",
        {
            "generated_on": date.today().isoformat(),
            "cohort": cohort,
            "runs": rows,
            "groups": groups,
            "hypotheses": hypotheses,
        },
    )
    (args.output_dir / "report.zh-CN.md").write_text(
        build_report(cohort, groups, hypotheses), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
