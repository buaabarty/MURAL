import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


binding = load_module(
    "human_binding", "artifacts/scripts/verify_human_window_binding.py"
)


def test_render_window_matches_annotation_packet_format():
    candidates = [
        {
            "file_path": "pkg/module.py",
            "signature": "pkg.module.target(value)",
        }
        for _ in range(20)
    ]
    rendered = binding.render_window(candidates)
    assert rendered.splitlines()[0] == "01. pkg/module.py :: pkg.module.target(value)"
    assert rendered.splitlines()[-1].startswith("20. ")


def test_method_mapping_keeps_raw_annotation_labels():
    assert binding.METHOD_TO_CONFIGURATION == {
        "BM25-local": "BM25_projection",
        "MURAL": "MURAL_BM25_structural",
    }
