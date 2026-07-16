import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

MODULE_DIR = Path(__file__).parent / "kgcompass"
sys.path.insert(0, str(MODULE_DIR))

from repair_claude import CodeRepair, load_instance_from_dataset

AUDIT_SCRIPT = Path(__file__).parent / "artifacts" / "scripts" / "audit_repair_context_rendering.py"


class RepairPromptContractTest(unittest.TestCase):
    def make_repairer(self):
        repairer = CodeRepair.__new__(CodeRepair)
        repairer.MAX_INPUT_LENGTH = 32768
        repairer.api_type = "openai_compat"
        repairer.model = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
        repairer.language = "python"
        return repairer

    def test_ranked_method_expands_to_named_base_commit_class(self):
        repairer = self.make_repairer()
        source = """class RegexValidator:
    def __call__(self, value):
        return bool(value)

class URLValidator(RegexValidator):
    regex = r'old'

    def validate(self, value):
        return self.regex.match(value)
"""
        expanded = repairer._expand_python_entity_context(
            {
                "signature": "pkg.URLValidator.__call__(self, value)",
                "name": "pkg.URLValidator.__call__",
                "file_path": "pkg/validators.py",
                # The archived method span can be stale or misresolved; the
                # qualified identity remains the stronger class-scope signal.
                "start_line": 2,
                "end_line": 3,
                "source_code": "    def __call__(self, value):\n        return bool(value)",
            },
            source,
        )
        self.assertEqual(expanded["_context_class"], "URLValidator")
        self.assertIn("regex = r'old'", expanded["source_code"])
        self.assertNotIn("return bool(value)", expanded["source_code"])

    def test_large_class_preserves_precise_ranked_method(self):
        repairer = self.make_repairer()
        body = "\n".join(f"    value_{index} = {index}" for index in range(220))
        source = f"class Large:\n{body}\n\n    def target(self):\n        return 1\n"
        lines = source.splitlines()
        target_line = next(
            index for index, line in enumerate(lines, 1) if "def target" in line
        )
        method_source = "    def target(self):\n        return 1"
        expanded = repairer._expand_python_entity_context(
            {
                "signature": "pkg.Large.target(self)",
                "file_path": "pkg/large.py",
                "start_line": target_line,
                "end_line": target_line + 1,
                "source_code": method_source,
            },
            source,
        )
        self.assertEqual(expanded["source_code"], method_source)
        self.assertNotIn("_context_class", expanded)

    def test_archived_top_level_snippet_is_rehydrated_from_base_commit(self):
        repairer = self.make_repairer()
        source = """def helper():
    return 0

def target(value):
    return value + 1
"""
        refreshed = repairer._rehydrate_python_entity_context(
            {
                "name": "pkg.module.target",
                "signature": "pkg.module.target(value)",
                "file_path": "pkg/module.py",
                "start_line": 1,
                "end_line": 2,
                "source_code": "def target(value):\n    return stale(value)",
            },
            source,
        )
        self.assertEqual(
            refreshed["source_code"], "def target(value):\n    return value + 1"
        )
        self.assertEqual((refreshed["start_line"], refreshed["end_line"]), (4, 5))

    def test_context_enrichment_rehydrates_every_top20_candidate_file(self):
        repairer = self.make_repairer()
        repairer._load_original_file_content = MagicMock(
            return_value=("def target():\n    return 1\n", None)
        )
        methods = [
            {
                "name": f"pkg.file_{index}.target",
                "signature": f"pkg.file_{index}.target()",
                "file_path": f"pkg/file_{index}.py",
                "start_line": 1,
                "end_line": 2,
                "source_code": "stale",
            }
            for index in range(12)
        ]
        enriched = repairer._enrich_methods_with_file_context(
            methods, "/repo", "base-commit"
        )
        self.assertEqual(repairer._load_original_file_content.call_count, 12)
        self.assertTrue(
            all("return 1" in item["source_code"] for item in enriched)
        )

    def test_explicit_full_profile_dispatches_to_full_builder(self):
        repairer = self.make_repairer()
        repairer._build_repair_context = MagicMock(return_value="full context")
        with patch.dict(
            os.environ,
            {"MURAL_REPAIR_FIRST_PROMPT_PROFILE": "full"},
            clear=False,
        ):
            content = repairer._build_first_repair_context("issue", [{"file_path": "a.py"}])
        self.assertEqual(content, "full context")
        repairer._build_repair_context.assert_called_once()

    def test_compact_selection_preserves_multiple_ranked_entities_per_file(self):
        repairer = self.make_repairer()
        methods = [
            {
                "file_path": "primary.py",
                "signature": f"primary.f{index}()",
                "start_line": index,
                "end_line": index,
                "source_code": f"def f{index}(): pass",
            }
            for index in range(1, 5)
        ]
        methods.append(
            {
                "file_path": "secondary.py",
                "signature": "secondary.target()",
                "start_line": 1,
                "end_line": 2,
                "source_code": "def target():\n    return 1",
            }
        )
        selected = repairer._build_ranked_context_items(methods)
        self.assertEqual(
            [item["signature"] for item in selected],
            [
                "primary.f1()",
                "primary.f2()",
                "primary.f3()",
                "primary.f4()",
                "secondary.target()",
            ],
        )
        self.assertEqual(
            [item["_prompt_mode"] for item in selected],
            ["primary", "secondary", "metadata", "metadata", "secondary"],
        )

    def test_compact_selection_deduplicates_expanded_class_context(self):
        repairer = self.make_repairer()
        methods = [
            {
                "file_path": "module.py",
                "signature": "module.Service.first()",
                "start_line": 1,
                "end_line": 20,
                "source_code": "class Service: pass",
                "_context_class": "Service",
            },
            {
                "file_path": "module.py",
                "signature": "module.Service.second()",
                "start_line": 1,
                "end_line": 20,
                "source_code": "class Service: pass",
                "_context_class": "Service",
            },
        ]
        selected = repairer._build_ranked_context_items(methods)
        self.assertEqual(len(selected), 2)
        self.assertEqual(
            [item["_prompt_mode"] for item in selected], ["primary", "metadata"]
        )

    def test_compact_selection_reserves_source_for_fused_tail(self):
        repairer = self.make_repairer()
        methods = []
        for index in range(20):
            band = "prefix" if index < 10 else "tail"
            methods.append(
                {
                    "file_path": f"{band}.py",
                    "signature": f"{band}.f{index}()",
                    "start_line": index + 1,
                    "end_line": index + 1,
                    "source_code": f"def f{index}(): pass",
                    "similarity": 2.0 - index / 100,
                }
            )
        selected = repairer._build_ranked_context_items(methods)
        tail_modes = [item["_prompt_mode"] for item in selected[10:]]
        self.assertEqual(tail_modes[:2], ["secondary", "secondary"])
        self.assertTrue(all(mode == "metadata" for mode in tail_modes[2:]))

    def test_prompt_and_completion_limits_are_explicitly_overridable(self):
        repairer = self.make_repairer()
        with patch.dict(
            os.environ,
            {
                "MURAL_REPAIR_PROMPT_TOKEN_LIMIT": "6000",
                "MURAL_REPAIR_COMPLETION_MAX_TOKENS": "2048",
            },
            clear=False,
        ):
            self.assertEqual(repairer._get_prompt_token_limit(), 6000)
            self.assertEqual(repairer._get_completion_max_tokens(), 2048)

    def test_invalid_first_prompt_profile_fails_closed(self):
        repairer = self.make_repairer()
        with patch.dict(
            os.environ,
            {"MURAL_REPAIR_FIRST_PROMPT_PROFILE": "adaptive"},
            clear=False,
        ):
            with self.assertRaises(ValueError):
                repairer._first_prompt_profile()

    def test_frozen_dataset_supplies_original_issue_and_commit(self):
        row = {
            "instance_id": "org__repo-1",
            "repo": "org/repo",
            "base_commit": "abc123",
            "problem_statement": "original issue text",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = os.path.join(temp_dir, "verified.jsonl")
            with open(dataset, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
            with patch.dict(os.environ, {"SWE_BENCH_LOCAL_FILE": dataset}):
                loaded = load_instance_from_dataset("org__repo-1", "swe-bench")

        self.assertEqual(loaded["repo_name"], "org/repo")
        self.assertEqual(loaded["commit_id"], "abc123")
        self.assertEqual(loaded["data"]["problem_statement"], "original issue text")

    def test_official_issue_precedes_location_fallback(self):
        repairer = self.make_repairer()
        repairer.count_tokens = lambda text: len(text.split())
        selected = repairer._select_problem_statement(
            {"issue": "location fallback"},
            {"data": {"problem_statement": "official issue"}},
        )
        self.assertEqual(selected, "official issue")

    def test_openai_compatible_generation_disables_prefill_by_default(self):
        repairer = self.make_repairer()
        repairer.code_block_lang = "python"
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(repairer._get_response_prefill(), "")

    def test_response_prefill_can_be_explicitly_enabled(self):
        repairer = self.make_repairer()
        repairer.code_block_lang = "python"
        with patch.dict(os.environ, {"MURAL_REPAIR_RESPONSE_PREFILL": "on"}):
            self.assertEqual(repairer._get_response_prefill(), "```python\n")

    def test_response_prefill_can_be_explicitly_disabled(self):
        repairer = self.make_repairer()
        repairer.code_block_lang = "python"
        with patch.dict(os.environ, {"MURAL_REPAIR_RESPONSE_PREFILL": "off"}):
            self.assertEqual(repairer._get_response_prefill(), "")

    def test_retry_limit_is_explicit_and_nonnegative(self):
        repairer = self.make_repairer()
        with patch.dict(os.environ, {"MURAL_REPAIR_MAX_RETRIES": "2"}):
            self.assertEqual(repairer._get_max_retries(), 2)
        with patch.dict(os.environ, {"MURAL_REPAIR_MAX_RETRIES": "-1"}):
            with self.assertRaises(ValueError):
                repairer._get_max_retries()

    def test_rendering_audit_preserves_duplicate_signatures(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("context_audit", AUDIT_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        content = """- signature : pkg.same()
- source_authority : authoritative-base-commit

- signature : pkg.same()
- source_mode : metadata-only
"""
        self.assertEqual(
            module.parse_rendered_blocks(content),
            [("pkg.same()", True), ("pkg.same()", False)],
        )

    def test_rendering_audit_maps_publication_and_run_variant_names(self):
        import argparse
        import importlib.util

        spec = importlib.util.spec_from_file_location("context_audit", AUDIT_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        args = argparse.Namespace(
            variants=["unused"],
            variant_specs=["issue=issue", "mural=mural3"],
        )
        self.assertEqual(
            module.parse_variant_specs(args),
            [("issue", "issue"), ("mural", "mural3")],
        )
        self.assertEqual(
            module.playground_repo_path(
                Path("/repos"), "mural3", "org__repo", True
            ),
            Path("/repos/org__repo"),
        )


if __name__ == "__main__":
    unittest.main()
