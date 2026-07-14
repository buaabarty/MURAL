import tempfile
import unittest
import os
import threading
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

MODULE_DIR = Path(__file__).parent / "kgcompass"
sys.path.insert(0, str(MODULE_DIR))

from fl import CodeAnalyzer
from knowledge_graph import KnowledgeGraph
from language_factory import JavaLanguageConfig

sys.path.insert(0, str(Path(__file__).parent / "artifacts/scripts"))
from export_java_kg_file_seeds import normalize_path, ranked_files
from evaluate_java_retrieve_localize import (
    FILE_FALLBACK_TARGET,
    instance_metrics,
    map_targets,
)


class JavaPathContractTest(unittest.TestCase):
    def test_auxiliary_patch_files_do_not_dilute_mapped_entities(self):
        entity = {
            "id": "method|src/main/java/Service.java|2|4|Service.run",
            "entity_type": "method",
            "file_path": "src/main/java/Service.java",
            "start_line": 2,
            "end_line": 4,
        }
        patch_text = """diff --git a/src/main/java/Service.java b/src/main/java/Service.java
--- a/src/main/java/Service.java
+++ b/src/main/java/Service.java
@@ -2,1 +2,1 @@
-old
+new
diff --git a/CHANGELOG.md b/CHANGELOG.md
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -1,1 +1,1 @@
-old
+new
"""
        targets, patched_files, fallback, unmapped = map_targets(
            patch_text, {"src/main/java/Service.java": [entity]}
        )
        self.assertEqual(targets, {entity["id"]})
        self.assertEqual(
            patched_files,
            {"src/main/java/Service.java", "CHANGELOG.md"},
        )
        self.assertFalse(fallback)
        self.assertEqual(unmapped, 1)

    def test_file_fallback_is_single_instance_level_target(self):
        patch_text = """diff --git a/src/main/java/NewType.java b/src/main/java/NewType.java
--- /dev/null
+++ b/src/main/java/NewType.java
@@ -0,0 +1,1 @@
+class NewType {}
"""
        targets, patched_files, fallback, unmapped = map_targets(patch_text, {})
        self.assertEqual(targets, {FILE_FALLBACK_TARGET})
        self.assertTrue(fallback)
        self.assertEqual(unmapped, 1)
        ranking = [
            {
                "id": "class|src/main/java/NewType.java|1|1|NewType",
                "file_path": "src/main/java/NewType.java",
            }
        ]
        metric = instance_metrics(
            ranking,
            targets,
            patched_files,
            file_fallback=True,
        )
        self.assertEqual(metric["method"], 1.0)
        self.assertEqual(metric["hit"], 1.0)

    def test_maven_source_root_and_member_resolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            service = repository / "module-a/src/main/java/org/acme/Service.java"
            service.parent.mkdir(parents=True)
            service.write_text("package org.acme; class Service {}\n", encoding="utf-8")

            config = JavaLanguageConfig()
            resolved = config.resolve_qualified_name_to_file_paths(
                str(repository), ["org", "acme", "Service", "run"]
            )
            self.assertEqual(resolved, [("file", str(service))])

    def test_exact_type_resolution_does_not_expand_parent_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            service = repository / "src/main/java/org/acme/Service.java"
            service.parent.mkdir(parents=True)
            service.write_text("package org.acme; class Service {}\n", encoding="utf-8")
            sibling = service.with_name("Sibling.java")
            sibling.write_text("package org.acme; class Sibling {}\n", encoding="utf-8")

            resolver_calls = []

            class Resolver:
                language = "java"

                @staticmethod
                def resolve_qualified_name_to_file_paths(_base_path, parts):
                    resolver_calls.append(tuple(parts))
                    if parts == ["org", "acme", "Service"]:
                        return [("file", str(service))]
                    return [("package", str(service.parent))]

            parser = SimpleNamespace(
                language_config=Resolver(),
                extract_classes=lambda _path: [{"name": "Service", "methods": []}],
                get_global_methods=lambda _path, _root: [],
                get_global_variables=lambda _path, _root: [],
            )
            analyzer = CodeAnalyzer.__new__(CodeAnalyzer)
            analyzer.config = {
                "repo_path": str(repository),
                "repo_root": str(repository),
            }
            analyzer.language_config = SimpleNamespace(
                config={"file_extensions": [".java"]}
            )
            analyzer.parser = parser
            analyzer.kg = MagicMock()
            analyzer.kg.search_file_by_path.return_value = None
            analyzer.searched_methods = set()
            analyzer.lock = threading.Lock()
            analyzer._parser_for_file = lambda _path: parser
            analyzer._build_file_class_methods = MagicMock()
            analyzer._search_method_by_name = MagicMock(return_value=[])

            analyzer._process_reference("root", ("import", "org.acme.Service"))

            self.assertEqual(resolver_calls, [("org", "acme", "Service")])
            analyzer.kg.link_issue_to_file.assert_called_once()
            self.assertEqual(
                analyzer.kg.link_issue_to_file.call_args.args[:2],
                ("root", "src/main/java/org/acme/Service.java"),
            )
            analyzer._build_file_class_methods.assert_called_once_with(str(service))

    def test_graph_paths_are_always_repository_relative(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "playground/example__repo"
            source = repository / "src/main/java/org/acme/Service.java"
            source.parent.mkdir(parents=True)
            source.write_text("class Service {}\n", encoding="utf-8")

            analyzer = CodeAnalyzer.__new__(CodeAnalyzer)
            analyzer.config = {"repo_path": str(repository)}
            expected = "src/main/java/org/acme/Service.java"
            self.assertEqual(analyzer._clean_path(str(source)), expected)
            self.assertEqual(analyzer._clean_path(expected), expected)

    def test_exporter_rejects_external_absolute_path(self):
        self.assertEqual(
            normalize_path(
                "/tmp/work/playground/example__repo/src/main/java/Service.java",
                "example__repo",
            ),
            "src/main/java/Service.java",
        )
        with self.assertRaises(ValueError):
            normalize_path("/tmp/work/src/main/java/Service.java", "example__repo")

    def test_direct_file_evidence_survives_parser_failure(self):
        payload = {
            "related_entities": {
                "files": [
                    {
                        "file_path": "src/Direct.java",
                        "distance": 1,
                        "support": 2,
                        "direct_anchor": True,
                    }
                ],
                "methods": [
                    {
                        "file_path": "src/Parsed.java",
                        "similarity": 0.9,
                    }
                ],
            }
        }
        rows = ranked_files(payload, "example__repo", depth=200, max_files=20)
        self.assertEqual([row["file_path"] for row in rows], [
            "src/Direct.java",
            "src/Parsed.java",
        ])
        self.assertTrue(rows[0]["direct_anchor"])
        self.assertIsNone(rows[0]["first_entity_rank"])

    def test_direct_file_ties_preserve_entity_relevance(self):
        payload = {
            "related_entities": {
                "files": [
                    {
                        "file_path": "src/Alphabetical.java",
                        "distance": 1,
                        "support": 1,
                        "direct_anchor": True,
                    },
                    {
                        "file_path": "src/Relevant.java",
                        "distance": 1,
                        "support": 1,
                        "direct_anchor": True,
                    },
                ],
                "methods": [
                    {
                        "file_path": "src/Relevant.java",
                        "similarity": 0.9,
                    }
                ],
            }
        }
        rows = ranked_files(payload, "example__repo", depth=50, max_files=20)
        self.assertEqual(
            [row["file_path"] for row in rows],
            ["src/Relevant.java", "src/Alphabetical.java"],
        )

    def test_call_edges_are_scoped_by_both_file_paths(self):
        class Result:
            @staticmethod
            def single():
                return None

        class Transaction:
            def __init__(self):
                self.query = ""
                self.parameters = {}

            def run(self, query, **parameters):
                self.query = query
                self.parameters = parameters
                return Result()

        transaction = Transaction()
        KnowledgeGraph._link_method_calls(
            transaction,
            "caller",
            "caller()",
            "callee",
            "callee()",
            "src/Caller.java",
            "src/Callee.java",
        )
        self.assertIn("caller.file_path = $caller_file_path", transaction.query)
        self.assertIn("callee.file_path = $callee_file_path", transaction.query)
        self.assertEqual(transaction.parameters["caller_file_path"], "src/Caller.java")
        self.assertEqual(transaction.parameters["callee_file_path"], "src/Callee.java")

    def test_directory_graph_uses_repository_relative_file_identity(self):
        class Transaction:
            def __init__(self):
                self.parameters = []

            def run(self, _query, **parameters):
                self.parameters.append(parameters)

        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "workspace/playground/example__repo"
            source = repository / "module/src/main/java/org/acme/Service.java"
            source.parent.mkdir(parents=True)
            source.write_text("class Service {}\n", encoding="utf-8")
            transaction = Transaction()
            with patch.dict(os.environ, {"KGCOMPASS_SOURCE_EXTENSIONS": ".java"}):
                KnowledgeGraph._create_directory_structure(
                    transaction,
                    str(repository / "module/src/main/java"),
                    str(repository),
                )
            file_paths = {
                parameters["file_path"]
                for parameters in transaction.parameters
                if "file_path" in parameters
            }
            self.assertEqual(
                file_paths,
                {"module/src/main/java/org/acme/Service.java"},
            )


if __name__ == "__main__":
    unittest.main()
