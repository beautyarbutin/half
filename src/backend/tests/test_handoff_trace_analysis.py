import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.handoff_trace_analysis import (
    acquire_codex_trace,
    aggregate_event_tables,
    analyze_trace,
    build_leakage_audit,
    extract_codex_usage,
)


def trace_line(payload):
    return json.dumps({"type": "response_item", "payload": payload})


class HandoffTraceAnalysisTests(unittest.TestCase):
    def test_classifies_reads_searches_tests_edits_and_rollbacks(self):
        trace = "\n".join(
            [
                trace_line(
                    {
                        "type": "function_call",
                        "name": "shell_command",
                        "arguments": json.dumps({"command": "Get-Content src/api.py"}),
                    }
                ),
                trace_line(
                    {
                        "type": "function_call",
                        "name": "shell_command",
                        "arguments": json.dumps({"command": "rg reserve_order src"}),
                    }
                ),
                trace_line(
                    {
                        "type": "function_call",
                        "name": "shell_command",
                        "arguments": json.dumps({"command": "rg reserve_order src"}),
                    }
                ),
                trace_line(
                    {
                        "type": "function_call",
                        "name": "apply_patch",
                        "arguments": "*** Update File: src/api.py",
                    }
                ),
                trace_line(
                    {
                        "type": "function_call",
                        "name": "shell_command",
                        "arguments": json.dumps({"command": "python -m pytest"}),
                    }
                ),
                trace_line(
                    {
                        "type": "function_call",
                        "name": "shell_command",
                        "arguments": json.dumps({"command": "git restore src/api.py"}),
                    }
                ),
            ]
        )

        result = analyze_trace(trace)

        self.assertEqual(result["counts"]["file_read_events"], 1)
        self.assertEqual(result["counts"]["search_events"], 2)
        self.assertEqual(result["counts"]["repeated_search_events"], 1)
        self.assertEqual(result["counts"]["test_runs"], 1)
        self.assertEqual(result["counts"]["edit_events"], 1)
        self.assertEqual(result["counts"]["rollback_events"], 1)
        self.assertEqual(result["counts"]["pre_edit_discovery_events"], 3)

    def test_leakage_audit_requires_complete_trace(self):
        audit = build_leakage_audit(
            trace_complete=False,
            omitted_fields=["risks"],
            canonical_handoff={"risks": "Never mutate the caller payload during reservation processing."},
            canaries={"risks": "TRACE-RISKS-C5V1"},
            visible_documents={"prompt": "visible prompt"},
            trace_reason="trace missing",
        )

        self.assertEqual(audit["status"], "unknown")
        self.assertEqual(audit["match_count"], 0)

    def test_leakage_audit_fails_on_omitted_canary(self):
        audit = build_leakage_audit(
            trace_complete=True,
            omitted_fields=["risks"],
            canonical_handoff={"risks": "Never mutate the caller payload during reservation processing."},
            canaries={"risks": "TRACE-RISKS-C5V1"},
            visible_documents={"tool_trace": "tool returned TRACE-RISKS-C5V1"},
        )

        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["matches"][0]["kind"], "canary")

    def test_complete_clean_trace_passes(self):
        audit = build_leakage_audit(
            trace_complete=True,
            omitted_fields=["risks"],
            canonical_handoff={"risks": "Never mutate the caller payload during reservation processing."},
            canaries={"risks": "TRACE-RISKS-C5V1"},
            visible_documents={"tool_trace": "read src/api.py"},
        )

        self.assertEqual(audit["status"], "passed")

    def test_aggregate_unique_files_deduplicates_across_attempts(self):
        attempts = [
            {
                "attempt_number": 1,
                "event_table": {
                    "counts": {"file_read_events": 1, "unique_files_read": 1},
                    "evidence": [
                        {"categories": ["file_read"], "paths": ["src/api.py"]}
                    ],
                },
            },
            {
                "attempt_number": 2,
                "event_table": {
                    "counts": {"file_read_events": 2, "unique_files_read": 1},
                    "evidence": [
                        {"categories": ["file_read"], "paths": ["src/api.py"]}
                    ],
                },
            },
        ]

        result = aggregate_event_tables(attempts)

        self.assertEqual(result["totals"]["file_read_events"], 3)
        self.assertEqual(result["totals"]["unique_files_read"], 1)

    def test_expands_nested_tools_from_exec_wrapper(self):
        source = (
            "await Promise.all(["
            "tools.shell_command({command: 'Get-Content src/a.py'}),"
            "tools.shell_command({command: 'python -m pytest'})"
            "]);"
        )
        trace = trace_line(
            {
                "type": "function_call",
                "name": "functions.exec",
                "arguments": json.dumps({"code": source}),
            }
        )

        result = analyze_trace(trace)

        self.assertEqual(result["counts"]["file_read_events"], 1)
        self.assertEqual(result["counts"]["test_runs"], 1)

    def test_acquires_codex_session_by_conversation_id_and_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session_dir = root / "sessions" / "2026" / "07" / "16"
            session_dir.mkdir(parents=True)
            path = session_dir / "rollout-2026-07-16T00-00-00-session-123.jsonl"
            lines = [
                json.dumps({"type": "session_meta", "payload": {"id": "session-123"}}),
                json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}}),
            ]
            path.write_text("\n".join(lines), encoding="utf-8")

            with patch.dict(os.environ, {"CODEX_HOME": str(root)}):
                trace = acquire_codex_trace("session-123", previous_cursor=1)

        self.assertTrue(trace["complete"])
        self.assertEqual(trace["cursor_start"], 1)
        self.assertEqual(trace["cursor_end"], 2)

    def test_extracts_latest_cumulative_codex_usage(self):
        trace = "\n".join(
            [
                json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2, "reasoning_output_tokens": 1, "total_tokens": 12}}}}),
                json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 25, "cached_input_tokens": 15, "output_tokens": 5, "reasoning_output_tokens": 3, "total_tokens": 30}}}}),
            ]
        )

        usage = extract_codex_usage(trace)

        self.assertEqual(
            usage,
            {
                "input_tokens": 25,
                "cached_input_tokens": 15,
                "output_tokens": 5,
                "reasoning_tokens": 3,
                "total_tokens": 30,
            },
        )


if __name__ == "__main__":
    unittest.main()
