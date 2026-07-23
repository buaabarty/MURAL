#!/usr/bin/env python3
"""Render the article-facing token-budget and target-scope figures."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt


WIDTH = 3.45
COLORS = {
    "BM25": "#5F6670",
    "Dense": "#168C8C",
    "MURAL": "#D55E00",
    "Hit": "#2F6B9A",
    "Complete": "#D55E00",
    "Grid": "#D9DDE2",
    "Text": "#20242A",
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
    mpl.rcParams.update(
        {
            "font.family": "STIXGeneral",
            "mathtext.fontset": "stix",
            "font.size": 8.0,
            "axes.labelsize": 8.0,
            "axes.edgecolor": COLORS["Text"],
            "axes.linewidth": 0.65,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "xtick.major.width": 0.65,
            "ytick.major.width": 0.65,
            "legend.fontsize": 7.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def finish_axes(ax: plt.Axes, grid_axis: str) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis=grid_axis, color=COLORS["Grid"], linewidth=0.55, zorder=0)
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
    indexed = {row["approach"]: row for row in rows}
    values: dict[str, list[float]] = {}
    for approach in ("BM25", "Dense", "MURAL"):
        values[approach] = []
        for budget in (2000, 4000, 8000):
            key = f"{approach}_t{budget}"
            if key not in indexed:
                raise ValueError(f"Missing token-budget row: {key}")
            values[approach].append(float(indexed[key]["hit"]))
    return values


def plot_token_budget(rows: list[dict[str, str]], output_dir: Path) -> None:
    values = token_budget_values(rows)
    x = [0.0, 1.0, 2.0]
    width = 0.22
    fig, ax = plt.subplots(figsize=(WIDTH, 2.18))

    groups = (
        ax.bar(
            [position - width for position in x],
            values["BM25"],
            width,
            label="MURAL (BM25)",
            color="white",
            edgecolor=COLORS["BM25"],
            linewidth=0.9,
            hatch="//",
            zorder=3,
        ),
        ax.bar(
            x,
            values["Dense"],
            width,
            label="MURAL (Dense)",
            color=COLORS["Dense"],
            edgecolor=COLORS["Dense"],
            linewidth=0.7,
            zorder=3,
        ),
        ax.bar(
            [position + width for position in x],
            values["MURAL"],
            width,
            label="MURAL",
            color=COLORS["MURAL"],
            edgecolor=COLORS["MURAL"],
            linewidth=0.7,
            zorder=3,
        ),
    )
    for group in groups:
        for rect in group:
            value = rect.get_height()
            ax.text(
                rect.get_x() + rect.get_width() / 2,
                value + 1.0,
                f"{value:.1f}",
                ha="center",
                va="bottom",
                fontsize=6.6,
                color=COLORS["Text"],
            )

    for position, mural, bm25 in zip(x, values["MURAL"], values["BM25"]):
        gain = (mural / bm25 - 1.0) * 100.0
        ax.text(
            position,
            84.0,
            f"+{gain:.1f}%",
            ha="center",
            va="center",
            fontsize=7.0,
            fontweight="bold",
            color=COLORS["MURAL"],
        )

    ax.set_ylabel("PromptHit (%)")
    ax.set_xlabel("Rendered-source budget")
    ax.set_xticks(x)
    ax.set_xticklabels(["2k", "4k", "8k"])
    ax.set_ylim(0, 89)
    ax.set_yticks([0, 20, 40, 60, 80])
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(0.0, 1.18),
        ncol=3,
        frameon=False,
        handlelength=1.3,
        handletextpad=0.35,
        columnspacing=0.85,
        borderaxespad=0,
    )
    finish_axes(ax, "y")
    fig.subplots_adjust(left=0.14, right=0.995, bottom=0.22, top=0.82)
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
    labels = [
        f"1 target\n(N={counts[0]})",
        f"2 targets\n(N={counts[1]})",
        f"3+ targets\n(N={counts[2]})",
    ]
    y = [2.0, 1.0, 0.0]
    height = 0.25
    fig, ax = plt.subplots(figsize=(WIDTH, 2.35))

    hit_bars = ax.barh(
        [position + height / 1.8 for position in y],
        hit,
        height,
        label="At least one target (Hit@20)",
        color=COLORS["Hit"],
        edgecolor=COLORS["Hit"],
        linewidth=0.6,
        zorder=3,
    )
    complete_bars = ax.barh(
        [position - height / 1.8 for position in y],
        complete,
        height,
        label="All targets (RefComplete)",
        color=COLORS["Complete"],
        edgecolor=COLORS["Complete"],
        linewidth=0.6,
        zorder=3,
    )
    for group in (hit_bars, complete_bars):
        for rect in group:
            ax.text(
                rect.get_width() + 1.2,
                rect.get_y() + rect.get_height() / 2,
                f"{rect.get_width():.1f}",
                ha="left",
                va="center",
                fontsize=6.8,
                color=COLORS["Text"],
            )

    for position, low, high in zip(y, complete, hit):
        gap = high - low
        if gap < 0.1:
            continue
        ax.annotate(
            "",
            xy=(high, position),
            xytext=(low, position),
            arrowprops={
                "arrowstyle": "|-|",
                "color": COLORS["BM25"],
                "linewidth": 0.75,
                "shrinkA": 0,
                "shrinkB": 0,
            },
        )
        ax.text(
            105.0,
            position,
            rf"$\Delta$ {gap:.1f}",
            ha="right",
            va="center",
            fontsize=6.8,
            color=COLORS["Text"],
        )

    ax.set_xlabel("Instances covered (%)")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlim(0, 108)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(0.0, 1.21),
        ncol=1,
        frameon=False,
        handlelength=1.35,
        handletextpad=0.4,
        labelspacing=0.25,
        borderaxespad=0,
    )
    finish_axes(ax, "x")
    fig.subplots_adjust(left=0.22, right=0.995, bottom=0.2, top=0.75)
    save_figure(fig, output_dir / "target_multiplicity_gap")


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    plot_token_budget(read_tsv(args.token_summary), args.output_dir)
    plot_target_multiplicity(read_tsv(args.multiplicity), args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
