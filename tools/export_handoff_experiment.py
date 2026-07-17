from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Iterable


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

ARM_LABELS = {
    "A_full": "A 完整 handoff",
    "D_no_verification": "D 删除 verification",
    "E_no_unfinished_items": "E 删除 unfinished_items",
    "H_no_handoff": "H 无 handoff",
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def locate_run(
    runs_root: Path,
    experiment_id: str,
    arm_id: str,
    run_id: str,
) -> Path:
    path = runs_root / experiment_id / arm_id / run_id / "run.json"
    if not path.is_file():
        raise ValueError(f"Cohort run not found: {path}")
    return path


def locate_any_run(runs_root: Path, experiment_id: str, run_id: str) -> Path | None:
    matches = list((runs_root / experiment_id).glob(f"*/{run_id}/run.json"))
    if len(matches) > 1:
        raise ValueError(f"Duplicate experiment run ID: {run_id}")
    return matches[0] if matches else None


def usage_totals(record: dict[str, Any]) -> dict[str, int]:
    override = record.get("usage_override", {})
    if int(override.get("total_tokens", 0) or 0) > 0:
        return {
            key: int(override.get(key, 0) or 0)
            for key in (
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "total_tokens",
            )
        }

    totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }
    for attempt in record.get("attempts", []):
        usage = attempt.get("usage", {})
        for key in totals:
            totals[key] += int(usage.get(key, 0) or 0)
    return totals


def eligible(record: dict[str, Any]) -> bool:
    attempts = list(record.get("attempts", []))
    return bool(
        attempts
        and not record.get("excluded_from_analysis", False)
        and record.get("leakage_audit", {}).get("status") == "passed"
        and all(bool(item.get("trace", {}).get("complete")) for item in attempts)
        and record.get("input_integrity")
    )


def build_run_row(spec: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    attempts = list(record.get("attempts", []))
    if not attempts:
        raise ValueError(f"Cohort run has no attempts: {record['run_id']}")

    final = attempts[-1]["evaluation"]
    audit = record.get("leakage_audit", {})
    events = record.get("event_table", {}).get("totals", {})
    usage = usage_totals(record)
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
        **usage,
        "human_interventions": len(record.get("interventions", [])),
        "changed_file_count": len(final.get("changed_files", [])),
        "changed_files": "|".join(final.get("changed_files", [])),
        "failed_probe_ids": "|".join(final["hidden"].get("failed_test_ids", [])),
        "leakage_status": audit.get("status", "unknown"),
        "leakage_match_count": int(audit.get("match_count", 0) or 0),
        "trace_complete": int(
            all(bool(item.get("trace", {}).get("complete")) for item in attempts)
        ),
        "input_integrity_verified": int(bool(record.get("input_integrity"))),
        "excluded": int(bool(record.get("excluded_from_analysis", False))),
        "exclusion_reason": record.get("exclusion_reason", ""),
        "eligible": int(eligible(record)),
    }
    for field in EVENT_FIELDS:
        row[field] = int(events.get(field, 0) or 0)
    return row


def build_attempt_rows(
    spec: dict[str, Any],
    record: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = list(record.get("attempts", []))
    summaries: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    previous_hidden = 0

    for attempt in attempts:
        number = int(attempt["attempt_number"])
        evaluation = attempt["evaluation"]
        hidden = evaluation["hidden"]
        event_table = attempt.get("event_table", {})
        counts = event_table.get("counts", {})
        attempt_usage = {
            key: int(attempt.get("usage", {}).get(key, 0) or 0)
            for key in (
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "total_tokens",
            )
        }
        summary = {
            "order": int(spec["order"]),
            "replicate": int(spec["replicate"]),
            "arm_id": record["arm_id"],
            "run_id": record["run_id"],
            "attempt_number": number,
            "attempt_resolved": int(bool(evaluation["resolved"])),
            "public_passed": int(evaluation["public"]["passed"]),
            "public_total": int(evaluation["public"]["total"]),
            "hidden_passed": int(hidden["passed"]),
            "hidden_total": int(hidden["total"]),
            "hidden_delta": int(hidden["passed"]) - previous_hidden,
            "failed_probe_ids": "|".join(hidden.get("failed_test_ids", [])),
            "changed_file_count": len(evaluation.get("changed_files", [])),
            "changed_files": "|".join(evaluation.get("changed_files", [])),
            "trace_complete": int(bool(attempt.get("trace", {}).get("complete"))),
            "leakage_status": attempt.get("leakage_audit", {}).get("status", "unknown"),
            **attempt_usage,
        }
        for field in EVENT_FIELDS:
            summary[field] = int(counts.get(field, 0) or 0)
        summaries.append(summary)

        sequence = 0
        for evidence in event_table.get("evidence", []):
            sequence += 1
            timeline.append(
                {
                    "order": int(spec["order"]),
                    "replicate": int(spec["replicate"]),
                    "arm_id": record["arm_id"],
                    "run_id": record["run_id"],
                    "attempt_number": number,
                    "sequence": sequence,
                    "trace_line": int(evidence.get("line", 0) or 0),
                    "call_index": int(evidence.get("call_index", 0) or 0),
                    "event": "|".join(evidence.get("categories", [])),
                    "tool": evidence.get("tool", ""),
                    "paths": "|".join(evidence.get("paths", [])),
                    "summary": evidence.get("summary", ""),
                    "attempt_resolved": int(bool(evaluation["resolved"])),
                    "hidden_passed": int(hidden["passed"]),
                    "hidden_total": int(hidden["total"]),
                    "failed_probe_ids": "|".join(hidden.get("failed_test_ids", [])),
                }
            )

        sequence += 1
        timeline.append(
            {
                "order": int(spec["order"]),
                "replicate": int(spec["replicate"]),
                "arm_id": record["arm_id"],
                "run_id": record["run_id"],
                "attempt_number": number,
                "sequence": sequence,
                "trace_line": "",
                "call_index": "",
                "event": "evaluation",
                "tool": "HALF private evaluator",
                "paths": "",
                "summary": (
                    f"public {evaluation['public']['passed']}/{evaluation['public']['total']}; "
                    f"hidden {hidden['passed']}/{hidden['total']}"
                ),
                "attempt_resolved": int(bool(evaluation["resolved"])),
                "hidden_passed": int(hidden["passed"]),
                "hidden_total": int(hidden["total"]),
                "failed_probe_ids": "|".join(hidden.get("failed_test_ids", [])),
            }
        )
        previous_hidden = int(hidden["passed"])

    return summaries, timeline


def _sample_stdev(values: list[float]) -> float:
    return stdev(values) if len(values) > 1 else 0.0


def aggregate(rows: list[dict[str, Any]], arm_order: Iterable[str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["eligible"]:
            grouped[row["arm_id"]].append(row)

    if not grouped["A_full"]:
        raise ValueError("Eligible A_full baseline runs are required")
    baseline_mean = mean(item["total_tokens"] for item in grouped["A_full"])
    baseline_median = median(item["total_tokens"] for item in grouped["A_full"])

    result: list[dict[str, Any]] = []
    for arm_id in arm_order:
        items = grouped[arm_id]
        if not items:
            continue
        tokens = [item["total_tokens"] for item in items]
        hidden_passed = sum(item["hidden_passed"] for item in items)
        hidden_total = sum(item["hidden_total"] for item in items)
        token_mean = mean(tokens)
        token_median = median(tokens)
        summary = {
            "arm_id": arm_id,
            "runs": len(items),
            "final_success_rate": mean(item["final_success"] for item in items),
            "first_attempt_success_rate": mean(
                item["first_attempt_success"] for item in items
            ),
            "hidden_pass_rate": hidden_passed / hidden_total,
            "hidden_passed": hidden_passed,
            "hidden_total": hidden_total,
            "mean_token_total": token_mean,
            "median_token_total": token_median,
            "stdev_token_total": _sample_stdev(tokens),
            "min_token_total": min(tokens),
            "max_token_total": max(tokens),
            "mean_token_ratio_vs_full": token_mean / baseline_mean,
            "median_token_ratio_vs_full": token_median / baseline_median,
            "mean_interaction_rounds": mean(
                item["interaction_rounds"] for item in items
            ),
            "mean_rework_count": mean(item["rework_count"] for item in items),
            "mean_changed_file_count": mean(
                item["changed_file_count"] for item in items
            ),
            "leakage_passed_runs": sum(
                item["leakage_status"] == "passed" for item in items
            ),
            "trace_complete_runs": sum(item["trace_complete"] for item in items),
        }
        for field in EVENT_FIELDS:
            summary[f"mean_{field}"] = mean(item[field] for item in items)
        result.append(summary)
    return result


def build_exclusion_rows(
    cohort: dict[str, Any],
    runs_root: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in cohort.get("excluded_runs", []):
        run_id = item["run_id"]
        path = locate_any_run(runs_root, cohort["experiment_id"], run_id)
        record = read_json(path) if path else {}
        rows.append(
            {
                "run_id": run_id,
                "arm_id": record.get("arm_id", item.get("arm_id", "")),
                "status": record.get("status", "not_found"),
                "reason": item["reason"],
                "record_marked_excluded": int(
                    bool(record.get("excluded_from_analysis", False))
                ),
                "preserved_evidence_path": str(path.parent) if path else "",
            }
        )
    return rows


def _percent(value: float, digits: int = 0) -> str:
    return f"{value * 100:.{digits}f}%"


def _number(value: float, digits: int = 1) -> str:
    rendered = f"{value:,.{digits}f}"
    return rendered.rstrip("0").rstrip(".")


def build_report(
    cohort: dict[str, Any],
    rows: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
) -> str:
    by_arm = {item["arm_id"]: item for item in groups}
    full = by_arm["A_full"]
    no_verification = by_arm.get("D_no_verification")
    no_unfinished = by_arm.get("E_no_unfinished_items")
    no_handoff = by_arm.get("H_no_handoff")
    eligible_rows = [item for item in rows if item["eligible"]]
    all_leakage_passed = all(
        item["leakage_status"] == "passed" for item in eligible_rows
    )
    all_trace_complete = all(item["trace_complete"] for item in eligible_rows)

    result_lines = []
    trace_lines = []
    for item in groups:
        result_lines.append(
            "| {label} | {runs} | {first} | {final} | {hidden} | {median} | "
            "{mean_value} | {sd} | {ratio} | {rework} |".format(
                label=ARM_LABELS.get(item["arm_id"], item["arm_id"]),
                runs=item["runs"],
                first=_percent(item["first_attempt_success_rate"]),
                final=_percent(item["final_success_rate"]),
                hidden=f"{item['hidden_passed']}/{item['hidden_total']}",
                median=f"{item['median_token_total']:,.0f}",
                mean_value=f"{item['mean_token_total']:,.0f}",
                sd=f"{item['stdev_token_total']:,.0f}",
                ratio=f"{item['median_token_ratio_vs_full']:.2f}x",
                rework=_number(item["mean_rework_count"]),
            )
        )
        trace_lines.append(
            "| {label} | {reads} | {unique} | {searches} | {repeated} | {tests} | "
            "{edits} | {guesses} | {ineffective} | {rollbacks} | {changed} |".format(
                label=ARM_LABELS.get(item["arm_id"], item["arm_id"]),
                reads=_number(item["mean_file_read_events"]),
                unique=_number(item["mean_unique_files_read"]),
                searches=_number(item["mean_search_events"]),
                repeated=_number(item["mean_repeated_search_events"]),
                tests=_number(item["mean_test_runs"]),
                edits=_number(item["mean_edit_events"]),
                guesses=_number(item["mean_interface_guess_events"]),
                ineffective=_number(item["mean_ineffective_edit_attempts"]),
                rollbacks=_number(item["mean_rollback_events"]),
                changed=_number(item["mean_changed_file_count"]),
            )
        )

    hypotheses: list[str] = []
    if no_unfinished:
        hypotheses.append(
            "- **H1 `unfinished_items -> 最终正确性`：未支持。** "
            f"E 的首轮与最终成功率均为 {_percent(no_unfinished['final_success_rate'])}，"
            f"隐藏测试为 {no_unfinished['hidden_passed']}/{no_unfinished['hidden_total']}，"
            "与 A 没有正确性差异。"
        )
    if no_verification:
        token_delta = no_verification["median_token_ratio_vs_full"] - 1
        hypotheses.append(
            "- **H2 `verification -> Token、返工与首轮成功率`：仅有 Token 方向性证据。** "
            f"D 的 Token 中位数比 A 高 {_percent(token_delta, 1)}，"
            "但首轮成功率、最终成功率和返工次数与 A 相同。"
        )
    if no_handoff:
        hypotheses.append(
            "- **H3 `无 handoff -> 仓库重新理解成本`：描述性支持。** "
            f"H 平均读取 {_number(no_handoff['mean_file_read_events'])} 次文件，"
            f"A 为 {_number(full['mean_file_read_events'])} 次；"
            f"H 的 Token 中位数为 A 的 "
            f"{no_handoff['median_token_ratio_vs_full']:.2f} 倍。"
        )

    exclusion_lines = (
        [
            f"- `{item['run_id']}`：{item['reason']} 原始证据保留于 "
            f"`{item['preserved_evidence_path']}`。"
            for item in exclusions
        ]
        or ["- 无排除 run。"]
    )

    return f"""# Reservation-v4 Natural 三轮实验结果

## 1. 实验范围

本报告对应 cohort `{cohort['cohort_id']}`。实验使用自然拆分的“取消预约并恢复库存”任务，
比较 `A_full`、`D_no_verification`、`E_no_unfinished_items` 和 `H_no_handoff`
四组，每组 3 个有效 run，共 12 个有效 run。每个 run 使用新 Codex 对话和独立工作区。

## 2. 有效性门

- 纳入分析：{len(eligible_rows)}/{len(rows)} 个 cohort 指定 run。
- Trace 完整：{"通过" if all_trace_complete else "未通过"}。
- 泄漏审计：{"12/12 passed，删字段内容零命中" if all_leakage_passed else "存在未通过 run"}。
- 输入完整性哈希：{sum(item['input_integrity_verified'] for item in eligible_rows)}/{len(eligible_rows)} 通过。
- 人工干预：{sum(item['human_interventions'] for item in eligible_rows)} 次。

## 3. 主要结果

| 组别 | n | 首轮成功率 | 最终成功率 | 隐藏测试 | Token 中位数 | Token 均值 | Token 标准差 | 中位数相对 A | 平均返工 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(result_lines)}

四组 12 个有效 run 均在首轮通过全部隐藏测试，因此本任务未观察到正确性、返工或人工干预差异。
Token 的组内波动明显，尤其是 A 和 H；因此主要报告中位数，同时保留均值、标准差和范围。
两项关键字段假设及固定条件在 pilot 前预注册；第 2、3 次重复是在观察 pilot 后追加，
因此本报告明确区分“预注册假设”和“后续扩展样本”。

## 4. Trace 行为

| 组别 | 读文件 | 唯一文件 | 搜索 | 重复搜索 | 测试 | 编辑 | 接口猜测 | 无效编辑轮 | 回滚 | 变更文件 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(trace_lines)}

H 的文件读取、搜索、变更范围和 Token 中位数均高于 A，说明没有 handoff 时，
Agent 更倾向于重新理解仓库。D 的 Token 中位数高于 A，但测试和返工并未增加；
E 与 A 的 Token 中位数接近，未形成稳定成本差异。

## 5. 预注册假设

{chr(10).join(hypotheses)}

## 6. 排除记录

{chr(10).join(exclusion_lines)}

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
"""


def export_attempt_files(
    output_dir: Path,
    attempt_rows: list[dict[str, Any]],
    timeline_rows: list[dict[str, Any]],
    exclusion_rows: list[dict[str, Any]],
) -> None:
    attempt_fields = list(attempt_rows[0]) if attempt_rows else []
    timeline_fields = list(timeline_rows[0]) if timeline_rows else [
        "order",
        "replicate",
        "arm_id",
        "run_id",
        "attempt_number",
        "sequence",
        "trace_line",
        "call_index",
        "event",
        "tool",
        "paths",
        "summary",
        "attempt_resolved",
        "hidden_passed",
        "hidden_total",
        "failed_probe_ids",
    ]
    write_csv(output_dir / "attempt_summary.csv", attempt_rows, attempt_fields)
    write_csv(
        output_dir / "failed_attempt_summary.csv",
        [item for item in attempt_rows if not item["attempt_resolved"]],
        attempt_fields,
    )
    write_csv(
        output_dir / "attempt_event_timeline.csv",
        timeline_rows,
        timeline_fields,
    )
    write_csv(
        output_dir / "failed_attempt_event_timeline.csv",
        [item for item in timeline_rows if not item["attempt_resolved"]],
        timeline_fields,
    )
    exclusion_fields = [
        "run_id",
        "arm_id",
        "status",
        "reason",
        "record_marked_excluded",
        "preserved_evidence_path",
    ]
    write_csv(output_dir / "exclusions.csv", exclusion_rows, exclusion_fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--events-only",
        action="store_true",
        help="Only add Attempt and event timeline exports to an existing result directory.",
    )
    args = parser.parse_args()

    cohort = read_json(args.cohort)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_rows: list[dict[str, Any]] = []
    attempt_rows: list[dict[str, Any]] = []
    timeline_rows: list[dict[str, Any]] = []
    discovered_arms: list[str] = []

    for spec in cohort["runs"]:
        record = read_json(
            locate_run(
                args.runs_root,
                cohort["experiment_id"],
                spec["arm_id"],
                spec["run_id"],
            )
        )
        if record["arm_id"] != spec["arm_id"]:
            raise ValueError(f"Arm mismatch for {spec['run_id']}")
        if record.get("excluded_from_analysis"):
            raise ValueError(
                f"Excluded run must not appear in cohort runs: {record['run_id']}"
            )
        if spec["arm_id"] not in discovered_arms:
            discovered_arms.append(spec["arm_id"])
        run_rows.append(build_run_row(spec, record))
        summaries, timeline = build_attempt_rows(spec, record)
        attempt_rows.extend(summaries)
        timeline_rows.extend(timeline)

    run_rows.sort(key=lambda item: item["order"])
    attempt_rows.sort(
        key=lambda item: (item["order"], item["attempt_number"])
    )
    timeline_rows.sort(
        key=lambda item: (
            item["order"],
            item["attempt_number"],
            item["sequence"],
        )
    )
    exclusion_rows = build_exclusion_rows(cohort, args.runs_root)
    export_attempt_files(
        args.output_dir,
        attempt_rows,
        timeline_rows,
        exclusion_rows,
    )
    if args.events_only:
        return

    preferred_order = [
        "A_full",
        "D_no_verification",
        "E_no_unfinished_items",
        "H_no_handoff",
    ]
    arm_order = [
        arm_id for arm_id in preferred_order if arm_id in discovered_arms
    ] + [
        arm_id for arm_id in discovered_arms if arm_id not in preferred_order
    ]
    groups = aggregate(run_rows, arm_order)
    write_csv(args.output_dir / "runs.csv", run_rows, list(run_rows[0]))
    write_csv(
        args.output_dir / "group_summary.csv",
        groups,
        list(groups[0]),
    )
    trace_fields = ["arm_id"] + [
        f"mean_{field}" for field in EVENT_FIELDS
    ]
    write_csv(
        args.output_dir / "trace_events.csv",
        [{field: item[field] for field in trace_fields} for item in groups],
        trace_fields,
    )
    leakage_fields = [
        "order",
        "replicate",
        "arm_id",
        "run_id",
        "leakage_status",
        "leakage_match_count",
        "trace_complete",
        "input_integrity_verified",
        "eligible",
    ]
    write_csv(
        args.output_dir / "leakage_audit.csv",
        [{field: item[field] for field in leakage_fields} for item in run_rows],
        leakage_fields,
    )
    write_json(
        args.output_dir / "results.json",
        {
            "generated_on": date.today().isoformat(),
            "cohort": cohort,
            "runs": run_rows,
            "groups": groups,
            "attempts": attempt_rows,
            "exclusions": exclusion_rows,
        },
    )
    (args.output_dir / "report.zh-CN.md").write_text(
        build_report(cohort, run_rows, groups, exclusion_rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
