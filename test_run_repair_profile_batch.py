import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "artifacts" / "scripts" / "run_repair_profile_batch.py"
SPEC = importlib.util.spec_from_file_location("run_repair_profile_batch", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RepairProfileBatchTest(unittest.TestCase):
    def test_provider_account_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repair.log"
            path.write_text('{"type": "insufficient_balance"}', encoding="utf-8")
            self.assertTrue(MODULE.provider_account_blocked(path))

    def make_args(self, **overrides):
        values = {
            "extra_body_json": None,
            "disable_thinking": False,
            "repetition_penalty": None,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_structured_flags_avoid_shell_json_contract(self):
        body = MODULE.build_extra_body(
            self.make_args(disable_thinking=True, repetition_penalty=1.05)
        )
        self.assertEqual(
            body, {"enable_thinking": False, "repetition_penalty": 1.05}
        )

    def test_structured_flags_override_json_values(self):
        body = MODULE.build_extra_body(
            self.make_args(
                extra_body_json=json.dumps(
                    {"enable_thinking": True, "repetition_penalty": 1.1}
                ),
                disable_thinking=True,
                repetition_penalty=1.2,
            )
        )
        self.assertEqual(
            body, {"enable_thinking": False, "repetition_penalty": 1.2}
        )

    def test_extra_body_must_be_json_object(self):
        with self.assertRaises(ValueError):
            MODULE.build_extra_body(self.make_args(extra_body_json="[]"))

    def test_protocol_defaults_match_glm52_snapshot(self):
        argv = [
            "run_repair_profile_batch.py",
            "--input-root",
            "input",
            "--output-root",
            "output",
            "--ids-file",
            "ids.txt",
            "--preset",
            "frozen_locations",
            "--playground-dir",
            "playgrounds",
            "--dataset-file",
            "verified.jsonl",
        ]
        with patch.object(MODULE.sys, "argv", argv):
            args = MODULE.parse_args()
        self.assertEqual(args.model, "glm-5.2")
        self.assertEqual(args.base_url, "https://www.autodl.art/api/v1")
        self.assertEqual(args.api_key_env, "AUTODL_API_KEY")
        self.assertEqual(args.variants, ["issue", "bm25", "mural"])
        self.assertEqual(args.first_prompt_profile, "compact")
        self.assertEqual(args.prompt_token_limit, 5000)
        self.assertEqual(args.completion_max_tokens, 2048)
        self.assertTrue(args.disable_thinking)


if __name__ == "__main__":
    unittest.main()
