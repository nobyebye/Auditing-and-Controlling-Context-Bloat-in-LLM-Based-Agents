"""CSV and SVG reporting helpers for thesis figures."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def write_summary_tables(summary: dict[str, Any], output_dir: str | Path) -> None:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    _write_group_csv(summary["by_configuration"], directory / "by_configuration.csv")
    _write_group_csv(summary["by_workflow_family"], directory / "by_workflow_family.csv")


def _write_group_csv(group: dict[str, dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "name",
        "invocations",
        "mean_total_tokens",
        "mean_total_chars",
        "mean_redundancy_ratio",
        "mean_unique_information_ratio",
        "duplicate_segment_count",
        "task_success_rate",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for name, values in group.items():
            writer.writerow({"name": name, **values})


def write_svg_bar_charts(summary: dict[str, Any], output_dir: str | Path) -> None:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    configs = summary["by_configuration"]
    _write_bar_chart(
        {name: values["mean_redundancy_ratio"] for name, values in configs.items()},
        directory / "redundancy_ratio_by_configuration.svg",
        "Mean Redundancy Ratio by Configuration",
        value_suffix="",
    )
    _write_bar_chart(
        {name: values["mean_total_tokens"] for name, values in configs.items()},
        directory / "tokens_by_configuration.svg",
        "Mean Total Tokens by Configuration",
        value_suffix=" tokens",
    )


def _write_bar_chart(values: dict[str, float], path: Path, title: str, value_suffix: str) -> None:
    width = 980
    row_height = 34
    left = 260
    top = 56
    bar_width = 580
    height = top + row_height * max(len(values), 1) + 36
    max_value = max(values.values(), default=1.0) or 1.0
    rows = []
    for idx, (name, value) in enumerate(values.items()):
        y = top + idx * row_height
        length = int((value / max_value) * bar_width)
        label = f"{value:.3f}{value_suffix}" if isinstance(value, float) else f"{value}{value_suffix}"
        rows.append(f'<text x="20" y="{y + 18}" font-size="13">{_escape(name)}</text>')
        rows.append(f'<rect x="{left}" y="{y}" width="{length}" height="22" fill="#2E74B5"/>')
        rows.append(f'<text x="{left + length + 8}" y="{y + 16}" font-size="12">{_escape(label)}</text>')

    svg = "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            f'<text x="20" y="30" font-size="18" font-weight="bold">{_escape(title)}</text>',
            *rows,
            "</svg>",
        ]
    )
    path.write_text(svg, encoding="utf-8")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
