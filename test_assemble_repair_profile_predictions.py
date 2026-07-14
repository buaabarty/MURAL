import argparse
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "artifacts" / "scripts" / "assemble_repair_profile_predictions.py"
SPEC = importlib.util.spec_from_file_location(
    "assemble_repair_profile_predictions", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RepairAssemblyAuditTest(unittest.TestCase):
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

    def test_frozen_protocol_audit_passes(self):
        MODULE.validate_audit(self.make_audit(), "mural", "org__repo-1", self.make_args())

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


if __name__ == "__main__":
    unittest.main()
