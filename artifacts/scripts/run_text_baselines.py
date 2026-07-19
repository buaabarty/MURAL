import argparse
import os
import subprocess
from pathlib import Path


COMPLETION_MARKER = "========== Figure 8 =========="


def run_cmd(cmd):
    print(f"$ {' '.join(cmd)}", flush=True)
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    subprocess.run(cmd, check=True, env=env)


def calc_done(log_file: Path) -> bool:
    if not log_file.exists():
        return False
    try:
        text = log_file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return COMPLETION_MARKER in text


def run_calc_prefl(base_dir: Path, run_id: str, log_dir: Path, resume: bool):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{run_id}.log"
    if resume and calc_done(log_file):
        print(f"===== Skip run-id {run_id} (completed log exists) =====", flush=True)
        return

    print(f"===== Running calc_prefl for run-id {run_id} =====", flush=True)
    cmd = [
        "python3",
        "-u",
        "kgcompass/calc_prefl.py",
        "--base-dir",
        str(base_dir),
        "--run-id",
        run_id,
    ]
    with log_file.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        fh.write(proc.stdout)
        print(proc.stdout, end="")
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "One-command interface for text retrieval baselines: "
            "export BM25/JinaDense/Hybrid JSONs and optionally run calc_prefl."
        )
    )
    parser.add_argument("--instance-ids", default="SWE-bench_Verified_ids.jsonl")
    parser.add_argument("--output", default="runs/text_baselines")
    parser.add_argument("--repos-dir", default="playground")
    parser.add_argument("--dataset-arrow", default=None)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--fusion-depth", type=int, default=200)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--embed-batch-size", type=int, default=1)
    parser.add_argument("--fetch-remote", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--exclude-hints",
        action="store_true",
        help="Do not use hints_text in query when exporting baselines.",
    )

    parser.add_argument("--bm25-tag", default="2000")
    parser.add_argument("--dense-tag", default="2001")
    parser.add_argument("--hybrid-tag", default="2002")

    parser.add_argument(
        "--with-calc-prefl",
        action="store_true",
        help="Run kgcompass/calc_prefl.py for the three baseline run-ids after export.",
    )
    parser.add_argument("--calc-log-dir", default="logs/calc_prefl_text")
    parser.add_argument("--calc-resume", action="store_true")

    args = parser.parse_args()

    export_cmd = [
        "python3",
        "-u",
        "export_text_baselines.py",
        "--output",
        args.output,
        "--repos-dir",
        args.repos_dir,
        "--instance-ids",
        args.instance_ids,
        "--top-k",
        str(args.top_k),
        "--fusion-depth",
        str(args.fusion_depth),
        "--embed-batch-size",
        str(args.embed_batch_size),
        "--bm25-tag",
        args.bm25_tag,
        "--dense-tag",
        args.dense_tag,
        "--hybrid-tag",
        args.hybrid_tag,
    ]

    if args.dataset_arrow:
        export_cmd.extend(["--dataset-arrow", args.dataset_arrow])
    if args.limit is not None:
        export_cmd.extend(["--limit", str(args.limit)])
    if args.fetch_remote:
        export_cmd.append("--fetch-remote")
    if args.force:
        export_cmd.append("--force")
    if args.exclude_hints:
        export_cmd.append("--exclude-hints")

    run_cmd(export_cmd)

    if not args.with_calc_prefl:
        print("Export finished.")
        return

    base_dir = Path(args.output)
    log_dir = Path(args.calc_log_dir)
    for run_id in [args.bm25_tag, args.dense_tag, args.hybrid_tag]:
        run_calc_prefl(base_dir, run_id, log_dir, args.calc_resume)

    print("All done: export + calc_prefl finished.")


if __name__ == "__main__":
    main()
