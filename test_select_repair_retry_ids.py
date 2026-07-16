import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parent / "artifacts" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "select_repair_retry_ids.py"
SPEC = importlib.util.spec_from_file_location("select_repair_retry_ids", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SelectRepairRetryIdsTest(unittest.TestCase):
    def write_run(self, root: Path, shard: str, error: str | None) -> None:
        patches = root / "issue" / shard / "issue" / "instance-1" / "patches"
        patches.mkdir(parents=True)
        (patches / "instance-1.run.json").write_text(
            json.dumps({"failed_files": [] if error is None else [{"error": error}]}),
            encoding="utf-8",
        )
        (patches / "patch_results.jsonl").write_text(
            json.dumps({"fix_patch": ""}) + "\n", encoding="utf-8"
        )

    def test_provider_failure_requires_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_run(root, "shard_0", "Connection error.")
            self.assertEqual(
                MODULE.classify_instance(root, "issue", "instance-1", ["shard_0"]),
                "retry",
            )

    def test_clean_retry_completes_failed_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_run(root, "shard_0", "insufficient_balance")
            self.write_run(root, "retry_1", None)
            self.assertEqual(
                MODULE.classify_instance(
                    root, "issue", "instance-1", ["shard_0", "retry_1"]
                ),
                "complete",
            )

    def test_incomplete_attempt_requires_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patches = root / "issue" / "retry_0" / "issue" / "instance-1" / "patches"
            patches.mkdir(parents=True)
            self.assertEqual(
                MODULE.classify_instance(root, "issue", "instance-1", ["retry_0"]),
                "retry",
            )


if __name__ == "__main__":
    unittest.main()
