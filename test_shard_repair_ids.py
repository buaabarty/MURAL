import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "artifacts" / "scripts" / "shard_repair_ids_by_repository.py"
SPEC = importlib.util.spec_from_file_location("shard_repair_ids", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ShardRepairIdsTest(unittest.TestCase):
    def test_repositories_are_not_split_and_load_is_balanced(self):
        ids = [
            "a__large-1",
            "a__large-2",
            "a__large-3",
            "b__small-1",
            "b__small-2",
            "c__tiny-1",
        ]
        shards = MODULE.partition_by_repository(ids, 2)
        locations = {}
        for shard_index, shard_ids in enumerate(shards):
            for instance_id in shard_ids:
                repository = MODULE.repository_of(instance_id)
                locations.setdefault(repository, set()).add(shard_index)
        self.assertTrue(all(len(indices) == 1 for indices in locations.values()))
        self.assertEqual(sorted(map(len, shards)), [3, 3])

    def test_rejects_nonpositive_shard_count(self):
        with self.assertRaises(ValueError):
            MODULE.partition_by_repository(["a__repo-1"], 0)


if __name__ == "__main__":
    unittest.main()
