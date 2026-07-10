import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import settings
from services.secure_handoff_experiment import (
    SCHEMA_FIELDS,
    prepare_run,
    secure_arm_options,
    summarize_experiment,
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
                    "max_attempts": 3,
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
        run = prepare_run("sample", "F_no_risks", model="test-model")
        workspace = Path(run["workspace"])
        run_dir = workspace.parent
        prompt = (run_dir / "prompt.txt").read_text(encoding="utf-8")

        self.assertTrue((workspace / "example.py").is_file())
        self.assertFalse((workspace / ".git").exists())
        self.assertIn(str(workspace), prompt)
        self.assertIn("Before reading or editing files, switch to that directory", prompt)
        self.assertIn("Finish the adapter", prompt)
        self.assertNotIn("Do not mutate input", prompt)
        self.assertNotIn("TRACE-risks", prompt)
        self.assertNotIn("canonical_handoff", prompt)

    def test_no_handoff_prompt_contains_no_canonical_values(self):
        run = prepare_run("sample", "H_no_handoff")
        prompt = (Path(run["workspace"]).parent / "prompt.txt").read_text(encoding="utf-8")

        self.assertIn("No predecessor handoff fields are visible", prompt)
        self.assertNotIn("Finish the adapter", prompt)
        self.assertNotIn("example.py", prompt)

    def test_summary_metrics_ignore_prepared_runs(self):
        attempted = prepare_run("sample", "A_full")
        prepare_run("sample", "A_full")
        run_path = Path(attempted["workspace"]).parent / "run.json"
        record = json.loads(run_path.read_text(encoding="utf-8"))
        record["status"] = "resolved"
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


if __name__ == "__main__":
    unittest.main()
