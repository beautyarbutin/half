import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import settings
from services.secure_handoff_experiment import (
    SCHEMA_FIELDS,
    _build_feedback,
    _public_record,
    _snapshot_workspace,
    exclude_run_from_analysis,
    evaluate_workspace,
    prepare_run,
    secure_arm_options,
    submit_manual_attempt,
    summarize_experiment,
    update_run_usage,
)


class SecureHandoffExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.private_root = root / "private"
        self.runs_root = root / "runs"
        self.fixture = root / "fixture"
        self.experiment = self.private_root / "sample"
        self.fixture.mkdir(parents=True)
        self.experiment.mkdir(parents=True)
        (self.fixture / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
        canonical = {
            "goal": "Finish the adapter",
            "changed_files": ["example.py"],
            "verification": "Public baseline passed",
            "unfinished_items": "Adapter remains",
            "risks": "Do not mutate input",
            "next_steps": "Call the existing service",
        }
        (self.experiment / "canonical_handoff.json").write_text(
            json.dumps(canonical),
            encoding="utf-8",
        )
        (self.experiment / "canaries.json").write_text(
            json.dumps({field: f"TRACE-{field}" for field in SCHEMA_FIELDS}),
            encoding="utf-8",
        )
        (self.experiment / "hidden_tests").mkdir()
        (self.experiment / "manifest.json").write_text(
            json.dumps(
                {
                    "experiment_id": "sample",
                    "fixture_repo": str(self.fixture),
                    "public_task": "Finish successor work.",
                    "canonical_handoff": "canonical_handoff.json",
                    "hidden_tests": "hidden_tests",
                    "forbidden_changed_files": ["src/example/completed.py"],
                    "max_attempts": 3,
                    "repair_signals": {
                        "test_unfinished_01_publishes_audit": "Review the audit contract dimensions."
                    },
                }
            ),
            encoding="utf-8",
        )
        self.old_private = settings.HANDOFF_EXPERIMENT_PRIVATE_ROOT
        self.old_runs = settings.HANDOFF_EXPERIMENT_RUNS_ROOT
        settings.HANDOFF_EXPERIMENT_PRIVATE_ROOT = str(self.private_root)
        settings.HANDOFF_EXPERIMENT_RUNS_ROOT = str(self.runs_root)

    def tearDown(self):
        settings.HANDOFF_EXPERIMENT_PRIVATE_ROOT = self.old_private
        settings.HANDOFF_EXPERIMENT_RUNS_ROOT = self.old_runs
        self.temporary.cleanup()

    def test_arm_catalog_has_leave_one_out_and_negative_control(self):
        arms = {arm["arm_id"]: arm for arm in secure_arm_options()}

        self.assertEqual(set(arms["A_full"]["include_fields"]), set(SCHEMA_FIELDS))
        self.assertNotIn("risks", arms["F_no_risks"]["include_fields"])
        self.assertEqual(arms["H_no_handoff"]["include_fields"], [])

    def test_prepare_run_materializes_only_filtered_prompt(self):
        generated_cache = self.fixture / ".hypothesis" / "constants"
        generated_cache.mkdir(parents=True)
        (generated_cache / "example").write_text("generated\n", encoding="utf-8")

        run = prepare_run("sample", "F_no_risks", model="test-model")
        workspace = Path(run["workspace"])
        run_dir = workspace.parent
        prompt = (run_dir / "prompt.txt").read_text(encoding="utf-8")

        self.assertTrue((workspace / "example.py").is_file())
        self.assertFalse((workspace / ".git").exists())
        self.assertFalse((workspace / ".hypothesis").exists())
        self.assertIn(str(workspace), prompt)
        self.assertIn("Before reading or editing files, switch to that directory", prompt)
        self.assertIn("Finish the adapter", prompt)
        self.assertNotIn("Do not mutate input", prompt)
        self.assertNotIn("TRACE-risks", prompt)
        self.assertNotIn("canonical_handoff", prompt)
        self.assertTrue((run_dir / "input_integrity.json").is_file())
        self.assertEqual(run["leakage_audit"]["status"], "unknown")

        runtime_cache = workspace / ".hypothesis" / "constants"
        runtime_cache.mkdir(parents=True)
        (runtime_cache / "runtime").write_text("generated\n", encoding="utf-8")
        self.assertNotIn(".hypothesis/constants/runtime", _snapshot_workspace(workspace))

    def test_prepare_run_supports_manifest_workspace_layout_and_test_command(self):
        manifest_path = self.experiment / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["workspace_markers"] = ["sqlite_utils/", "tests/", "setup.py"]
        manifest["public_test_command"] = "python -m pytest -q"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        run = prepare_run("sample", "A_full")
        prompt = (Path(run["workspace"]).parent / "prompt.txt").read_text(
            encoding="utf-8"
        )

        self.assertIn("`sqlite_utils/`, `tests/`, `setup.py`", prompt)
        self.assertIn("## Public verification command", prompt)
        self.assertIn("`python -m pytest -q`", prompt)
        self.assertNotIn("`src/`, `tests/`, and `pyproject.toml`", prompt)

    def test_no_handoff_prompt_contains_no_canonical_values(self):
        run = prepare_run("sample", "H_no_handoff")
        prompt = (Path(run["workspace"]).parent / "prompt.txt").read_text(encoding="utf-8")

        self.assertIn("No predecessor handoff fields are visible", prompt)
        self.assertNotIn("Finish the adapter", prompt)
        self.assertNotIn("example.py", prompt)

    def test_evaluator_uses_manifest_forbidden_file_list(self):
        run = prepare_run("sample", "A_full")
        workspace = Path(run["workspace"])
        completed = workspace / "src" / "example" / "completed.py"
        completed.parent.mkdir(parents=True)
        completed.write_text("CHANGED = True\n", encoding="utf-8")

        evaluation = evaluate_workspace(
            json.loads((workspace.parent / "run.json").read_text(encoding="utf-8")),
            1,
        )

        self.assertEqual(
            evaluation["forbidden_files_touched"],
            ["src/example/completed.py"],
        )

    def test_summary_metrics_ignore_prepared_runs(self):
        attempted = prepare_run("sample", "A_full")
        prepare_run("sample", "A_full")
        run_path = Path(attempted["workspace"]).parent / "run.json"
        record = json.loads(run_path.read_text(encoding="utf-8"))
        record["status"] = "resolved"
        record["leakage_audit"] = {"status": "passed", "attempts": []}
        record["attempts"] = [
            {
                "usage": {"total_tokens": 123},
                "evaluation": {"resolved": True},
            }
        ]
        run_path.write_text(json.dumps(record), encoding="utf-8")

        summary = summarize_experiment("sample")
        arm = summary["by_arm"]["A_full"]

        self.assertEqual(arm["runs"], 2)
        self.assertEqual(arm["prepared_runs"], 1)
        self.assertEqual(arm["attempted_runs"], 1)
        self.assertEqual(arm["clean_runs"], 1)
        self.assertEqual(arm["first_attempt_resolved"], 1)
        self.assertEqual(arm["final_resolved"], 1)
        self.assertEqual(arm["token_total"], 123)

    def test_public_record_hides_private_evaluator_details(self):
        run = prepare_run("sample", "A_full")
        run_path = Path(run["workspace"]).parent / "run.json"
        record = json.loads(run_path.read_text(encoding="utf-8"))
        record["attempts"] = [
            {
                "attempt_number": 1,
                "usage": {"total_tokens": 0},
                "workspace_before": {"secret.py": "before"},
                "workspace_after": {"secret.py": "after"},
                "trace": {"source": "manual", "source_path": "C:/private/session.jsonl"},
                "leakage_audit": {
                    "status": "failed",
                    "matches": [
                        {
                            "field": "unfinished_items",
                            "source": "tool_trace",
                            "kind": "canary",
                            "value": "private canary",
                        }
                    ],
                },
                "evaluation": {
                    "resolved": False,
                    "public": {
                        "passed": 1,
                        "failed": 0,
                        "skipped": 2,
                        "total": 1,
                        "failed_test_ids": [],
                        "cases": [{"name": "public_case"}],
                        "output_tail": "public internals",
                    },
                    "hidden": {
                        "passed": 0,
                        "failed": 1,
                        "skipped": 0,
                        "total": 1,
                        "failed_test_ids": ["test_unfinished_01_publishes_audit"],
                        "cases": [{"name": "secret_case"}],
                        "output_tail": "expected secret value",
                    },
                    "probe_scores": {"unfinished_items": {"passed": 0, "total": 1}},
                    "changed_files": ["example.py"],
                    "forbidden_files_touched": [],
                },
            }
        ]

        public = _public_record(record)
        public_evaluation = public["attempts"][0]["evaluation"]

        self.assertNotIn("cases", public_evaluation["hidden"])
        self.assertNotIn("output_tail", public_evaluation["hidden"])
        self.assertNotIn("workspace_before", public["attempts"][0])
        self.assertNotIn("workspace_after", public["attempts"][0])
        self.assertNotIn("source_path", public["attempts"][0]["trace"])
        self.assertNotIn("value", public["attempts"][0]["leakage_audit"]["matches"][0])
        self.assertEqual(
            public_evaluation["hidden"]["failed_test_ids"],
            ["test_unfinished_01_publishes_audit"],
        )
        self.assertEqual(public_evaluation["public"]["skipped"], 2)

    def test_feedback_adds_non_secret_focus_and_repeat_count(self):
        run = prepare_run("sample", "A_full")
        run_path = Path(run["workspace"]).parent / "run.json"
        record = json.loads(run_path.read_text(encoding="utf-8"))
        failed_evaluation = {
            "public": {"failed_test_ids": []},
            "hidden": {"failed_test_ids": ["test_unfinished_01_publishes_audit"]},
        }
        record["attempts"] = [
            {"evaluation": failed_evaluation},
            {"evaluation": failed_evaluation},
        ]

        feedback = _build_feedback(record, record["attempts"][-1])

        self.assertIn("consecutive failure 2", feedback)
        self.assertIn("Review the audit contract dimensions.", feedback)
        self.assertNotIn("expected secret value", feedback)

    def test_submit_attempt_writes_audit_and_event_artifacts(self):
        run = prepare_run("sample", "F_no_risks")
        trace = "\n".join(
            [
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "shell_command",
                            "arguments": json.dumps({"command": "python -m pytest"}),
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 100,
                                    "cached_input_tokens": 80,
                                    "output_tokens": 23,
                                    "reasoning_output_tokens": 5,
                                    "total_tokens": 123,
                                }
                            },
                        },
                    }
                ),
            ]
        )
        evaluation = {
            "resolved": True,
            "public": {
                "passed": 1,
                "failed": 0,
                "total": 1,
                "failed_test_ids": [],
                "cases": [],
                "output_tail": "",
            },
            "hidden": {
                "passed": 1,
                "failed": 0,
                "total": 1,
                "failed_test_ids": [],
                "cases": [],
                "output_tail": "",
            },
            "probe_scores": {},
            "changed_files": ["example.py"],
            "forbidden_files_touched": [],
        }

        with patch(
            "services.secure_handoff_experiment.evaluate_workspace",
            return_value=evaluation,
        ):
            result = submit_manual_attempt(
                run["run_id"],
                conversation_id="test-session",
                trace_jsonl=trace,
                trace_complete=True,
                agent_output="Completed without hidden handoff values.",
            )

        run_dir = Path(run["workspace"]).parent
        attempt_dir = run_dir / "attempts" / "attempt-1"
        self.assertEqual(result["leakage_audit"]["status"], "passed")
        self.assertEqual(result["event_table"]["totals"]["test_runs"], 1)
        self.assertEqual(result["metrics"]["token_total"], 123)
        self.assertTrue(result["metrics"]["token_observed"])
        self.assertTrue((attempt_dir / "tool_trace.jsonl").is_file())
        self.assertTrue((attempt_dir / "workspace_before.json").is_file())
        self.assertTrue((attempt_dir / "workspace_after.json").is_file())
        self.assertTrue((run_dir / "leakage_audit.json").is_file())
        self.assertTrue((run_dir / "event_table.json").is_file())

    def test_update_run_usage_does_not_create_or_evaluate_attempt(self):
        run = prepare_run("sample", "A_full")
        evaluation = {
            "resolved": True,
            "public": {"passed": 1, "failed": 0, "total": 1, "failed_test_ids": [], "cases": [], "output_tail": ""},
            "hidden": {"passed": 1, "failed": 0, "total": 1, "failed_test_ids": [], "cases": [], "output_tail": ""},
            "probe_scores": {},
            "changed_files": ["example.py"],
            "forbidden_files_touched": [],
        }
        with patch(
            "services.secure_handoff_experiment.evaluate_workspace",
            return_value=evaluation,
        ) as evaluator:
            submit_manual_attempt(run["run_id"], agent_output="Completed.")
            result = update_run_usage(run["run_id"], {"total_tokens": 456})

        self.assertEqual(evaluator.call_count, 1)
        self.assertEqual(result["metrics"]["interaction_rounds"], 1)
        self.assertEqual(result["metrics"]["token_total"], 456)
        self.assertTrue(result["metrics"]["token_observed"])
        self.assertTrue((Path(run["workspace"]).parent / "usage.json").is_file())

    def test_excluded_run_is_not_eligible_or_aggregated(self):
        run = prepare_run("sample", "A_full")
        evaluation = {
            "resolved": True,
            "public": {"passed": 1, "failed": 0, "total": 1, "failed_test_ids": [], "cases": [], "output_tail": ""},
            "hidden": {"passed": 1, "failed": 0, "total": 1, "failed_test_ids": [], "cases": [], "output_tail": ""},
            "probe_scores": {},
            "changed_files": ["example.py"],
            "forbidden_files_touched": [],
        }
        with patch("services.secure_handoff_experiment.evaluate_workspace", return_value=evaluation):
            submit_manual_attempt(run["run_id"], agent_output="Completed.")
        excluded = exclude_run_from_analysis(run["run_id"], "operator created duplicate")
        summary = summarize_experiment("sample")

        self.assertFalse(excluded["metrics"]["eligible_for_analysis"])
        self.assertEqual(summary["by_arm"]["A_full"]["excluded_runs"], 1)
        self.assertEqual(summary["by_arm"]["A_full"]["attempted_runs"], 0)

    def test_submit_attempt_requires_agent_output(self):
        run = prepare_run("sample", "A_full")

        with self.assertRaisesRegex(ValueError, "Agent final output is required"):
            submit_manual_attempt(run["run_id"], agent_output="   ")


if __name__ == "__main__":
    unittest.main()
