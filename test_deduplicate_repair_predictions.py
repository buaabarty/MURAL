import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "artifacts" / "scripts" / "deduplicate_repair_predictions.py"
SPEC = importlib.util.spec_from_file_location("deduplicate_repair_predictions", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RepairPredictionDeduplicationTest(unittest.TestCase):
    def test_identical_patches_share_one_canonical_slot(self):
        predictions = {
            "issue": {
                "a": {"model_patch": "patch-a"},
                "b": {"model_patch": ""},
            },
            "bm25": {
                "a": {"model_patch": "patch-a"},
                "b": {"model_patch": "patch-b"},
            },
            "mural": {
                "a": {"model_patch": "patch-c"},
                "b": {"model_patch": "patch-b"},
            },
        }
        slots, mapping = MODULE.assign_slots(
            predictions, ["issue", "bm25", "mural"]
        )
        self.assertEqual([len(slot) for slot in slots], [2, 1, 0])
        a_rows = [row for row in mapping if row["instance_id"] == "a"]
        self.assertEqual([row["slot"] for row in a_rows], [0, 0, 1])
        self.assertEqual(
            [row["reused_identical_patch"] for row in a_rows], [0, 1, 0]
        )
        b_rows = [row for row in mapping if row["instance_id"] == "b"]
        self.assertEqual([row["slot"] for row in b_rows], ["", 0, 0])

    def test_variant_id_mismatch_fails_closed(self):
        predictions = {
            "issue": {"a": {"model_patch": "patch-a"}},
            "mural": {"b": {"model_patch": "patch-b"}},
        }
        with self.assertRaisesRegex(ValueError, "prediction IDs do not match"):
            MODULE.assign_slots(predictions, ["issue", "mural"])

    def test_reuse_requires_identical_prompt_when_audit_is_supplied(self):
        predictions = {
            "issue": {"a": {"model_patch": "patch-a"}},
            "bm25": {"a": {"model_patch": "patch-a"}},
            "mural": {"a": {"model_patch": "patch-a"}},
        }
        prompt_hashes = {
            ("issue", "a"): "1" * 64,
            ("bm25", "a"): "2" * 64,
            ("mural", "a"): "2" * 64,
        }
        slots, mapping = MODULE.assign_slots(
            predictions,
            ["issue", "bm25", "mural"],
            prompt_hashes,
        )
        self.assertEqual([len(slot) for slot in slots], [1, 1, 0])
        self.assertEqual([row["slot"] for row in mapping], [0, 1, 1])
        self.assertEqual(
            [row["reused_identical_patch"] for row in mapping],
            [0, 0, 1],
        )
        self.assertEqual(
            [row["prompt_sha256"] for row in mapping],
            ["1" * 64, "2" * 64, "2" * 64],
        )


if __name__ == "__main__":
    unittest.main()
