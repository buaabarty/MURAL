import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parent / "artifacts" / "scripts" / "assemble_repair_profile_predictions.py"
SPEC = importlib.util.spec_from_file_location("assemble_repair_profile_predictions", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AssembleRepairProfilePredictionsTest(unittest.TestCase):
    def make_args(self, **overrides):
        values = {
            "expected_dataset_source": "/data/verified.jsonl",
            "expected_context_profile": "rank_stratified_v3_allfiles",
            "expected_max_retries": 1,
            "max_prompt_tokens": 5000,
            "require_no_prefill": True,
            "require_thinking_disabled": True,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def make_audit(self, **overrides):
        values = {
            "dataset_source": "/data/verified.jsonl",
            "problem_statement_tokens": 100,
            "context_profile_version": "rank_stratified_v3_allfiles",
            "candidate_entity_count": 20,
            "first_prompt_rendered_entity_count": 18,
            "first_prompt_source_entity_count": 8,
            "first_prompt_tokens": 4999,
            "response_prefill": False,
            "max_retries": 1,
            "generation_extra_body": {"enable_thinking": False},
        }
        values.update(overrides)
        return values

    def write_run(self, root: Path, shard: str, error: str | None) -> Path:
        run_dir = root / "issue" / shard / "issue"
        patches = run_dir / "instance-1" / "patches"
        patches.mkdir(parents=True)
        audit = {
            "failed_files": [] if error is None else [{"error": error}],
            "final_status": "success" if error is None else "failed",
        }
        (patches / "instance-1.run.json").write_text(
            json.dumps(audit), encoding="utf-8"
        )
        (patches / "patch_results.jsonl").write_text(
            json.dumps({"fix_patch": ""}) + "\n", encoding="utf-8"
        )
        return run_dir

    def test_variant_mapping(self):
        args = argparse.Namespace(
            variants=["unused"],
            variant_specs=["issue=issue", "mural=mural3"],
        )
        self.assertEqual(
            MODULE.parse_variant_specs(args),
            [("issue", "issue"), ("mural", "mural3")],
        )

    def test_frozen_protocol_audit_passes(self):
        MODULE.validate_audit(
            self.make_audit(), "mural", "org__repo-1", self.make_args()
        )

    def test_stale_context_profile_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Unexpected context profile"):
            MODULE.validate_audit(
                self.make_audit(context_profile_version="legacy"),
                "mural",
                "org__repo-1",
                self.make_args(),
            )

    def test_rendered_source_count_cannot_exceed_rendered_entities(self):
        with self.assertRaisesRegex(ValueError, "Inconsistent context"):
            MODULE.validate_audit(
                self.make_audit(first_prompt_source_entity_count=19),
                "mural",
                "org__repo-1",
                self.make_args(),
            )

    def test_thinking_must_be_explicitly_disabled(self):
        with self.assertRaisesRegex(ValueError, "Thinking was not explicitly disabled"):
            MODULE.validate_audit(
                self.make_audit(generation_extra_body={}),
                "mural",
                "org__repo-1",
                self.make_args(),
            )

    def test_selects_provider_clean_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_run(root, "shard_0", "Error type: insufficient_balance")
            expected = self.write_run(root, "retry_1", None)
            selected = MODULE.select_sharded_run_dir(
                root, "issue", "issue", "instance-1", ["shard_0", "retry_1"]
            )
            self.assertEqual(selected, expected)

    def test_rejects_two_provider_clean_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_run(root, "shard_0", None)
            self.write_run(root, "retry_1", None)
            with self.assertRaisesRegex(ValueError, "one provider-clean run"):
                MODULE.select_sharded_run_dir(
                    root, "issue", "issue", "instance-1", ["shard_0", "retry_1"]
                )


if __name__ == "__main__":
    unittest.main()
