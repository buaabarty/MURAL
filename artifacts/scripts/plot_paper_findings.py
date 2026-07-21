#!/usr/bin/env python3
"""Render the article-facing token-budget and target-scope figures."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import font_manager


WIDTH = 3.45
COLORS = {
    "BM25": "#4D4D4D",
    "Dense": "#0072B2",
    "MURAL": "#D55E00",
    "Complete": "#D55E00",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-summary", type=Path, required=True)
    parser.add_argument("--multiplicity", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def configure_matplotlib() -> None:
    paper_fonts = [
        Path(path) for path in font_manager.findSystemFonts() if Path(path).name.startswith("Tinos-")
    ]
    for path in paper_fonts:
        font_manager.fontManager.addfont(path)
    mpl.rcParams.update(
        {
            "font.family": "Tinos" if paper_fonts else "DejaVu Serif",
            "font.size": 8.0,
            "axes.labelsize": 8.5,
            "axes.linewidth": 0.7,
            "axes.unicode_minus": False,
            "xtick.labelsize": 7.8,
            "ytick.labelsize": 7.8,
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "legend.fontsize": 7.4,
            "lines.linewidth": 1.6,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "mathtext.fontset": "stix",
        }
    )


def finish_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(direction="out", length=3.0, pad=2.0)
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.55, alpha=0.8, zorder=0)
    ax.set_axisbelow(True)


def save_figure(fig: plt.Figure, output_stem: Path) -> None:
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output_stem.with_suffix(".pdf"),
        bbox_inches="tight",
        pad_inches=0.025,
        metadata={
            "Title": output_stem.name,
            "Creator": "MURAL artifact plot_paper_findings.py",
            "CreationDate": None,
            "ModDate": None,
        },
    )
    fig.savefig(
        output_stem.with_suffix(".png"),
        dpi=300,
        bbox_inches="tight",
        pad_inches=0.025,
    )
    plt.close(fig)


def token_budget_values(rows: list[dict[str, str]]) -> dict[str, list[float]]:
    budgets = (2000, 4000, 8000)
    approaches = ("BM25", "Dense", "MURAL")
    indexed = {row["approach"]: row for row in rows}
    values: dict[str, list[float]] = {}
    for approach in approaches:
        values[approach] = []
        for budget in budgets:
            key = f"{approach}_t{budget}"
            if key not in indexed:
                raise ValueError(f"Missing token-budget row: {key}")
            values[approach].append(float(indexed[key]["hit"]))
    return values


def plot_token_budget(rows: list[dict[str, str]], output_dir: Path) -> None:
    values = token_budget_values(rows)
    x = [0, 1, 2]
    styles = {
        "BM25": ("s", "--", "BM25 projection"),
        "Dense": ("^", "-.", "Dense projection"),
        "MURAL": ("o", "-", "MURAL"),
    }

    fig, ax = plt.subplots(figsize=(WIDTH, 2.18))
    for approach in ("BM25", "Dense", "MURAL"):
        marker, linestyle, label = styles[approach]
        ax.plot(
            x,
            values[approach],
            color=COLORS[approach],
            linestyle=linestyle,
            marker=marker,
            markersize=5.1,
            markerfacecolor=COLORS[approach] if approach == "MURAL" else "white",
            markeredgewidth=1.0,
            label=label,
            zorder=3 if approach == "MURAL" else 2,
        )

    for position, mural, bm25 in zip(x, values["MURAL"], values["BM25"]):
        ax.text(
            position,
            mural + 1.55,
            f"+{mural - bm25:.1f}",
            color=COLORS["MURAL"],
            fontsize=7.4,
            fontweight="bold",
            ha="center",
            va="bottom",
        )

    ax.set_xlim(-0.18, 2.18)
    ax.set_ylim(40, 80)
    ax.set_yticks([40, 50, 60, 70, 80])
    ax.set_xticks(x, ["2k", "4k", "8k"])
    ax.set_xlabel("Rendered-token budget")
    ax.set_ylabel("Hit (%)")
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.015),
        ncol=3,
        frameon=False,
        handlelength=1.8,
        handletextpad=0.35,
        columnspacing=0.85,
        borderaxespad=0,
    )
    finish_axes(ax)
    fig.subplots_adjust(left=0.16, right=0.99, bottom=0.22, top=0.84)
    save_figure(fig, output_dir / "token_budget_hit")


def multiplicity_values(
    rows: list[dict[str, str]],
) -> tuple[list[int], list[float], list[float]]:
    indexed = {row["target_count"]: row for row in rows}
    groups = ("1", "2", "3+")
    missing = [group for group in groups if group not in indexed]
    if missing:
        raise ValueError(f"Missing target-multiplicity rows: {missing}")
    counts = [int(indexed[group]["N"]) for group in groups]
    hit = [float(indexed[group]["hit"]) for group in groups]
    complete = [float(indexed[group]["complete"]) for group in groups]
    return counts, hit, complete


def plot_target_multiplicity(rows: list[dict[str, str]], output_dir: Path) -> None:
    counts, hit, complete = multiplicity_values(rows)
    x = [0, 1, 2]

    fig, ax = plt.subplots(figsize=(WIDTH, 2.28))
    ax.fill_between(x, complete, hit, color="#D9D9D9", alpha=0.45, zorder=1)
    ax.plot(
        x,
        hit,
        color=COLORS["Dense"],
        linestyle="-",
        marker="o",
        markersize=5.2,
        markerfacecolor=COLORS["Dense"],
        label="Hit@20",
        zorder=3,
    )
    ax.plot(
        x,
        complete,
        color=COLORS["Complete"],
        linestyle="--",
        marker="s",
        markersize=4.8,
        markerfacecolor="white",
        markeredgewidth=1.0,
        label="RefComplete",
        zorder=3,
    )

    ax.text(0, hit[0] + 4.0, f"{hit[0]:.1f} (both)", ha="center", va="bottom", fontsize=7.2)
    for position in (1, 2):
        ax.text(position, hit[position] + 3.0, f"{hit[position]:.1f}", ha="center", fontsize=7.2)
        ax.text(
            position,
            complete[position] - 8.5 if position == 1 else complete[position] + 3.8,
            f"{complete[position]:.1f}",
            color=COLORS["Complete"],
            ha="center",
            va="center",
            fontsize=7.2,
        )
        ax.text(
            position + 0.05,
            (hit[position] + complete[position]) / 2,
            f"{hit[position] - complete[position]:.1f}-pt gap",
            color="#555555",
            ha="center",
            va="center",
            fontsize=6.9,
        )

    ax.set_xlim(-0.18, 2.23)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_xticks(x, [f"1\n(N={counts[0]})", f"2\n(N={counts[1]})", f"3+\n(N={counts[2]})"])
    ax.set_xlabel("Number of strict repair targets")
    ax.set_ylabel("Instance coverage (%)")
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.015),
        ncol=2,
        frameon=False,
        handlelength=2.0,
        handletextpad=0.4,
        columnspacing=1.3,
        borderaxespad=0,
    )
    finish_axes(ax)
    fig.subplots_adjust(left=0.16, right=0.99, bottom=0.27, top=0.84)
    save_figure(fig, output_dir / "target_multiplicity_gap")


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    plot_token_budget(read_tsv(args.token_summary), args.output_dir)
    plot_target_multiplicity(read_tsv(args.multiplicity), args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
