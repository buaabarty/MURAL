#!/usr/bin/env python3
"""Run the structural localizer for one Java instance at a fixed graph depth."""

from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--depth", required=True, type=int)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    module_dir = args.source_root.resolve() / "kgcompass"
    sys.path.insert(0, str(module_dir))
    import config  # type: ignore  # Imported after the source path is installed.

    config.SEARCH_SPACE = args.depth
    sys.argv = [
        str(module_dir / "fl.py"),
        args.instance_id,
        args.repo_id,
        str(args.output_dir.resolve()),
        "multi-swe-bench",
    ]
    runpy.run_path(str(module_dir / "fl.py"), run_name="__main__")


if __name__ == "__main__":
    main()
