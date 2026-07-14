import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "artifacts" / "scripts" / "collect_swebench_reports.py"


class CollectSwebenchReportsTest(unittest.TestCase):
    def test_normalizes_nonempty_reports_and_skips_empty_patches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictions = root / "predictions.jsonl"
            rows = [
                {
                    "instance_id": "owner__repo-1",
                    "model_name_or_path": "model/name",
                    "model_patch": "diff --git a/x b/x\n",
                },
                {
                    "instance_id": "owner__repo-2",
                    "model_name_or_path": "model/name",
                    "model_patch": "",
                },
            ]
            predictions.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            report_dir = root / "logs" / "run" / "model__name" / "owner__repo-1"
            report_dir.mkdir(parents=True)
            (report_dir / "report.json").write_text(
                json.dumps(
                    {
                        "owner__repo-1": {
                            "patch_successfully_applied": True,
                            "resolved": True,
                            "tests_status": {
                                "FAIL_TO_PASS": {"success": ["a"], "failure": []},
                                "PASS_TO_PASS": {"success": ["b", "c"], "failure": []},
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            output = root / "official.jsonl"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--predictions",
                    str(predictions),
                    "--logs-root",
                    str(root / "logs"),
                    "--run-id",
                    "run",
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0]["resolved"])
            self.assertEqual(result[0]["fail_to_pass_success"], 1)
            self.assertEqual(result[0]["pass_to_pass_success"], 2)

    def test_missing_report_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictions = root / "predictions.jsonl"
            predictions.write_text(
                json.dumps(
                    {
                        "instance_id": "owner__repo-1",
                        "model_name_or_path": "model",
                        "model_patch": "patch",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--predictions",
                    str(predictions),
                    "--logs-root",
                    str(root / "logs"),
                    "--run-id",
                    "run",
                    "--output",
                    str(root / "official.jsonl"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing 1 reports", result.stderr)

    def test_normalizes_only_confirmed_terminal_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictions = root / "predictions.jsonl"
            rows = [
                {
                    "instance_id": "owner__repo-apply",
                    "model_name_or_path": "model",
                    "model_patch": "malformed patch",
                },
                {
                    "instance_id": "owner__repo-timeout",
                    "model_name_or_path": "model",
                    "model_patch": "applicable patch",
                },
            ]
            predictions.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            apply_dir = root / "logs" / "run" / "model" / "owner__repo-apply"
            timeout_dir = root / "logs" / "run" / "model" / "owner__repo-timeout"
            apply_dir.mkdir(parents=True)
            timeout_dir.mkdir(parents=True)
            (apply_dir / "run_instance.log").write_text(
                ">>>>> Patch Apply Failed:\nmalformed patch\n", encoding="utf-8"
            )
            (timeout_dir / "run_instance.log").write_text(
                "Test timed out after 1800 seconds.\n", encoding="utf-8"
            )
            output = root / "official.jsonl"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--predictions",
                    str(predictions),
                    "--logs-root",
                    str(root / "logs"),
                    "--run-id",
                    "run",
                    "--output",
                    str(output),
                    "--normalize-terminal-errors",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            normalized = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual([row["error"] for row in normalized], [
                "patch_apply_failed",
                "test_timeout",
            ])
            self.assertFalse(normalized[0]["patch_successfully_applied"])
            self.assertTrue(normalized[1]["patch_successfully_applied"])
            summary = json.loads(result.stdout)
            self.assertEqual(summary["normalized_terminal"], 2)
            self.assertEqual(summary["missing"], 0)

    def test_infrastructure_error_is_not_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictions = root / "predictions.jsonl"
            predictions.write_text(
                json.dumps(
                    {
                        "instance_id": "owner__repo-1",
                        "model_name_or_path": "model",
                        "model_patch": "patch",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            log_dir = root / "logs" / "run" / "model" / "owner__repo-1"
            log_dir.mkdir(parents=True)
            (log_dir / "run_instance.log").write_text(
                "toomanyrequests: registry rate limit\n", encoding="utf-8"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--predictions",
                    str(predictions),
                    "--logs-root",
                    str(root / "logs"),
                    "--run-id",
                    "run",
                    "--output",
                    str(root / "official.jsonl"),
                    "--normalize-terminal-errors",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing 1 reports", result.stderr)


if __name__ == "__main__":
    unittest.main()
