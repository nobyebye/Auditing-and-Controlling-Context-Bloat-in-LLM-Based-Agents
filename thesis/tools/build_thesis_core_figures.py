"""Generate the three editable core thesis figures as SVG and PNG."""

from __future__ import annotations

import argparse
import html
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PALETTE = {
    "ink": "#17212B",
    "muted": "#53616F",
    "line": "#425466",
    "paper": "#FFFFFF",
    "soft": "#F4F6F8",
    "blue": "#DDEBF2",
    "blue_strong": "#347A91",
    "green": "#E3EFE4",
    "green_strong": "#3E7C59",
    "orange": "#F6E6D8",
    "orange_strong": "#B86132",
    "purple": "#E9E4F1",
    "purple_strong": "#6E568B",
    "red": "#F4DEDE",
    "red_strong": "#A84242",
    "gold": "#F4ECD4",
    "gold_strong": "#8D6B18",
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = Path(
        r"C:\Windows\Fonts\arialbd.ttf"
        if bold
        else r"C:\Windows\Fonts\arial.ttf"
    )
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for explicit_line in text.splitlines():
        words = explicit_line.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            width = draw.textbbox((0, 0), candidate, font=font)[2]
            if width <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


class DualCanvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.image = Image.new("RGB", (width, height), PALETTE["paper"])
        self.draw = ImageDraw.Draw(self.image)
        self.svg: list[str] = [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            ),
            "<defs>",
            (
                '<marker id="arrow" markerWidth="10" markerHeight="8" '
                'refX="9" refY="4" orient="auto">'
                f'<path d="M0,0 L10,4 L0,8 Z" fill="{PALETTE["line"]}"/>'
                "</marker>"
            ),
            "</defs>",
            f'<rect width="{width}" height="{height}" fill="{PALETTE["paper"]}"/>',
        ]

    def rect(
        self,
        xy: tuple[int, int, int, int],
        *,
        fill: str,
        stroke: str = PALETTE["line"],
        width: int = 3,
        radius: int = 10,
    ) -> None:
        self.draw.rounded_rectangle(
            xy, radius=radius, fill=fill, outline=stroke, width=width
        )
        x1, y1, x2, y2 = xy
        self.svg.append(
            (
                f'<rect x="{x1}" y="{y1}" width="{x2 - x1}" height="{y2 - y1}" '
                f'rx="{radius}" fill="{fill}" stroke="{stroke}" '
                f'stroke-width="{width}"/>'
            )
        )

    def line(
        self,
        points: list[tuple[int, int]],
        *,
        fill: str = PALETTE["line"],
        width: int = 5,
        arrow: bool = False,
    ) -> None:
        self.draw.line(points, fill=fill, width=width, joint="curve")
        if arrow and len(points) >= 2:
            (x1, y1), (x2, y2) = points[-2], points[-1]
            angle = math.atan2(y2 - y1, x2 - x1)
            length = 18
            wing = 10
            left = (
                x2 - length * math.cos(angle) + wing * math.sin(angle),
                y2 - length * math.sin(angle) - wing * math.cos(angle),
            )
            right = (
                x2 - length * math.cos(angle) - wing * math.sin(angle),
                y2 - length * math.sin(angle) + wing * math.cos(angle),
            )
            self.draw.polygon([(x2, y2), left, right], fill=fill)
        point_text = " ".join(f"{x},{y}" for x, y in points)
        marker = ' marker-end="url(#arrow)"' if arrow else ""
        self.svg.append(
            f'<polyline points="{point_text}" fill="none" stroke="{fill}" '
            f'stroke-width="{width}" stroke-linejoin="round"{marker}/>'
        )

    def circle(
        self,
        center: tuple[int, int],
        radius: int,
        *,
        fill: str,
        stroke: str = PALETTE["line"],
        width: int = 3,
    ) -> None:
        x, y = center
        self.draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=fill,
            outline=stroke,
            width=width,
        )
        self.svg.append(
            f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{width}"/>'
        )

    def text(
        self,
        center: tuple[int, int],
        text: str,
        *,
        size: int,
        color: str = PALETTE["ink"],
        bold: bool = False,
        max_width: int | None = None,
        line_gap: int = 8,
    ) -> None:
        font = _font(size, bold)
        width = max_width or self.width
        lines = _wrap(self.draw, text, font, width)
        line_height = size + line_gap
        block_height = len(lines) * line_height - line_gap
        x, y = center
        top = y - block_height / 2
        for index, line in enumerate(lines):
            bbox = self.draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            baseline_y = top + index * line_height
            self.draw.text(
                (x - text_width / 2, baseline_y),
                line,
                font=font,
                fill=color,
            )
            escaped = html.escape(line)
            svg_y = baseline_y + size
            weight = "700" if bold else "400"
            self.svg.append(
                f'<text x="{x}" y="{svg_y}" text-anchor="middle" '
                f'font-family="Arial" font-size="{size}" font-weight="{weight}" '
                f'fill="{color}">{escaped}</text>'
            )

    def box(
        self,
        xy: tuple[int, int, int, int],
        title: str,
        body: str,
        *,
        fill: str,
        accent: str,
        title_size: int = 25,
        body_size: int = 20,
    ) -> None:
        self.rect(xy, fill=fill, stroke=accent, width=3, radius=10)
        x1, y1, x2, y2 = xy
        self.rect(
            (x1, y1, x2, y1 + 52),
            fill=accent,
            stroke=accent,
            width=0,
            radius=8,
        )
        self.text(
            ((x1 + x2) // 2, y1 + 26),
            title,
            size=title_size,
            color=PALETTE["paper"],
            bold=True,
            max_width=x2 - x1 - 24,
        )
        self.text(
            ((x1 + x2) // 2, (y1 + 52 + y2) // 2),
            body,
            size=body_size,
            color=PALETTE["ink"],
            max_width=x2 - x1 - 30,
            line_gap=7,
        )

    def save(self, base_path: Path) -> None:
        base_path.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(base_path.with_suffix(".png"), dpi=(200, 200))
        svg_text = "\n".join([*self.svg, "</svg>"])
        base_path.with_suffix(".svg").write_text(svg_text, encoding="utf-8")


def research_overview(output_dir: Path) -> None:
    canvas = DualCanvas(1900, 1080)
    canvas.text(
        (950, 55),
        "Research overview: auditing and controlling context bloat in LLM-based agents",
        size=34,
        bold=True,
        max_width=1760,
    )
    canvas.text(
        (950, 105),
        "Automatically constructed context is the research object; avoidable bloat is the central problem.",
        size=22,
        color=PALETTE["muted"],
        max_width=1700,
    )

    source_boxes = [
        ((55, 190, 350, 310), "Retrieval", "Retrieved passages", PALETTE["blue"], PALETTE["blue_strong"]),
        ((55, 340, 350, 460), "Memory", "Stored facts and summaries", PALETTE["green"], PALETTE["green_strong"]),
        ((55, 490, 350, 610), "Tool outputs", "Observations and structured data", PALETTE["orange"], PALETTE["orange_strong"]),
        ((55, 640, 350, 760), "History", "Conversation and generated traces", PALETTE["purple"], PALETTE["purple_strong"]),
    ]
    for xy, title, body, fill, accent in source_boxes:
        canvas.box(xy, title, body, fill=fill, accent=accent)
        canvas.line([(350, (xy[1] + xy[3]) // 2), (455, 475)], arrow=True)

    canvas.box(
        (470, 220, 850, 730),
        "Model-visible context",
        "",
        fill=PALETTE["soft"],
        accent=PALETTE["line"],
        title_size=27,
        body_size=23,
    )
    canvas.text(
        (660, 370),
        "System + user + framework\n+ retrieval + memory\n+ tools + generated traces",
        size=22,
        bold=True,
        max_width=320,
    )
    canvas.box(
        (515, 500, 805, 690),
        "Context bloat",
        "Duplicate\nIrrelevant or stale\nVerbose\nCross-source accumulation",
        fill=PALETTE["red"],
        accent=PALETTE["red_strong"],
        title_size=24,
        body_size=19,
    )

    canvas.line([(850, 475), (965, 475)], arrow=True)
    canvas.box(
        (980, 190, 1360, 760),
        "Runtime auditing",
        "1  Capture before each LLM call\n\n2  Attribute source provenance\n\n3  Detect and localize bloat\n\n4  Measure tokens, ratios, and growth",
        fill=PALETTE["blue"],
        accent=PALETTE["blue_strong"],
        title_size=28,
        body_size=21,
    )

    canvas.line([(1360, 365), (1475, 365)], arrow=True)
    canvas.box(
        (1490, 190, 1845, 505),
        "Source-aware control",
        "Remove exact duplicates\nFilter stale or irrelevant context\nCompress verbose tool output",
        fill=PALETTE["green"],
        accent=PALETTE["green_strong"],
        title_size=25,
        body_size=20,
    )
    canvas.line([(1667, 505), (1667, 585)], arrow=True)
    canvas.box(
        (1490, 600, 1845, 800),
        "Joint evaluation",
        "Efficiency: tokens, cost, latency\nUtility: task success and non-inferiority",
        fill=PALETTE["gold"],
        accent=PALETTE["gold_strong"],
        title_size=25,
        body_size=20,
    )

    canvas.rect(
        (110, 885, 1790, 1010),
        fill=PALETTE["soft"],
        stroke=PALETTE["line"],
        radius=8,
    )
    stages = [
        ("RQ1", "Detect and localize", PALETTE["blue_strong"]),
        ("RQ2", "Measure quantitatively", PALETTE["purple_strong"]),
        ("RQ3", "Explain sources and patterns", PALETTE["orange_strong"]),
        ("RQ4", "Mitigate without unacceptable task loss", PALETTE["green_strong"]),
    ]
    x_positions = [300, 690, 1110, 1545]
    for index, ((rq, label, color), x) in enumerate(zip(stages, x_positions)):
        canvas.circle((x - 100, 947), 38, fill=color, stroke=color)
        canvas.text((x - 100, 947), rq, size=20, color=PALETTE["paper"], bold=True)
        canvas.text((x + 70, 947), label, size=20, bold=True, max_width=260)
        if index < len(stages) - 1:
            canvas.line([(x + 210, 947), (x_positions[index + 1] - 155, 947)], arrow=True, width=4)
    canvas.save(output_dir / "figure_1_1_research_overview")


def experiment_workflow(output_dir: Path) -> None:
    canvas = DualCanvas(1900, 1120)
    canvas.text(
        (950, 55),
        "Independent validation workflow",
        size=36,
        bold=True,
        max_width=1700,
    )
    canvas.text(
        (950, 105),
        "Controlled consistency, independent annotation, and utility-aware intervention",
        size=22,
        color=PALETTE["muted"],
        max_width=1650,
    )

    canvas.box(
        (55, 180, 405, 430),
        "Shared infrastructure",
        "Schema 1.2 request envelope\nClient-side payload hash\nSource-attributed segments\nImmutable manifests and call ledger",
        fill=PALETTE["soft"],
        accent=PALETTE["line"],
        title_size=25,
        body_size=19,
    )

    study_boxes = [
        (
            (480, 165, 900, 445),
            "Study A  Controlled",
            "Injected perturbations\n1,188 completed runs\n1,596 invocation traces\nPurpose: pipeline consistency",
            PALETTE["blue"],
            PALETTE["blue_strong"],
        ),
        (
            (945, 165, 1365, 445),
            "Study B  Natural traces",
            "60 held-out public tasks\n2 execution paths / 120 contexts\nTwo independent annotators\nPurpose: RQ1-RQ3 validity",
            PALETTE["purple"],
            PALETTE["purple_strong"],
        ),
        (
            (1410, 165, 1830, 445),
            "Study C  Intervention",
            "108 counterfactual calls\n180 mitigation replays\nEqual-budget LLMLingua-2\nPurpose: RQ2 and RQ4 utility",
            PALETTE["orange"],
            PALETTE["orange_strong"],
        ),
    ]
    for xy, title, body, fill, accent in study_boxes:
        canvas.box(
            xy,
            title,
            body,
            fill=fill,
            accent=accent,
            title_size=24,
            body_size=19,
        )
    canvas.line(
        [(405, 305), (440, 305), (440, 140), (1620, 140)],
        arrow=False,
        width=4,
    )
    for center_x in (690, 1155, 1620):
        canvas.line([(center_x, 140), (center_x, 165)], arrow=True, width=4)

    canvas.line([(690, 445), (690, 555)], arrow=True, width=4)
    canvas.line([(1155, 445), (1155, 555)], arrow=True, width=4)
    canvas.line([(1620, 445), (1620, 555)], arrow=True, width=4)
    canvas.text(
        (950, 565),
        "Evidence namespaces remain separate",
        size=22,
        bold=True,
        color=PALETTE["muted"],
    )

    evidence_boxes = [
        ((75, 635, 480, 860), "Injected", "Designed fixture labels\nInternal consistency only", PALETTE["blue"], PALETTE["blue_strong"]),
        ((525, 635, 930, 860), "Heuristic", "Detector indicators\nPrecision, recall, localization", PALETTE["purple"], PALETTE["purple_strong"]),
        ((975, 635, 1380, 860), "Human reference", "Blind keep / remove labels\nAgreement before adjudication", PALETTE["green"], PALETTE["green_strong"]),
        ((1425, 635, 1830, 860), "Counterfactual", "Paired removals\nTask utility and non-inferiority", PALETTE["gold"], PALETTE["gold_strong"]),
    ]
    for xy, title, body, fill, accent in evidence_boxes:
        canvas.box(xy, title, body, fill=fill, accent=accent, title_size=26, body_size=20)
        canvas.line([(950, 590), ((xy[0] + xy[2]) // 2, 620)], arrow=True, width=4)

    canvas.rect(
        (210, 960, 1690, 1060),
        fill=PALETTE["soft"],
        stroke=PALETTE["line"],
        radius=8,
    )
    canvas.text(
        (950, 1010),
        "Task-cluster statistics -> evidence builders -> scoped RQ answers with uncertainty",
        size=24,
        bold=True,
        max_width=1400,
    )
    for xy, *_ in evidence_boxes:
        canvas.line(
            [((xy[0] + xy[2]) // 2, 860), ((xy[0] + xy[2]) // 2, 930), (950, 930), (950, 960)],
            arrow=False,
            width=3,
        )
    canvas.save(output_dir / "figure_4_1_experimental_workflow")


def graphical_abstract(output_dir: Path) -> None:
    canvas = DualCanvas(1900, 1190)
    canvas.text(
        (950, 55),
        "Graphical abstract: evidence for detecting, measuring, and mitigating context bloat",
        size=34,
        bold=True,
        max_width=1770,
    )

    metrics = [
        ("1,596", "Study A traces", PALETTE["blue_strong"]),
        ("120", "Study B final contexts", PALETTE["purple_strong"]),
        ("288", "Study C planned calls", PALETTE["orange_strong"]),
        ("4", "separate evidence types", PALETTE["green_strong"]),
    ]
    metric_x = [270, 720, 1170, 1620]
    for (value, label, color), x in zip(metrics, metric_x):
        canvas.rect((x - 180, 120, x + 180, 260), fill=PALETTE["soft"], stroke=color, radius=8)
        canvas.text((x, 170), value, size=38, bold=True, color=color)
        canvas.text((x, 225), label, size=20, bold=True, max_width=320)

    canvas.text(
        (950, 315),
        "Automatically constructed context -> source-aware runtime audit -> evidence-linked conclusions",
        size=25,
        bold=True,
        color=PALETTE["muted"],
        max_width=1700,
    )

    rq_boxes = [
        (
            (70, 380, 910, 610),
            "RQ1  EXTERNAL VALIDATION PENDING",
            "Study A macro-F1: 1.000 against injected labels\nThis verifies pipeline consistency only\nNatural-trace accuracy requires Study B annotations",
            PALETTE["blue"],
            PALETTE["blue_strong"],
        ),
        (
            (990, 380, 1830, 610),
            "RQ2  INDEPENDENT AGREEMENT PENDING",
            "Study A measured vs injected ratio: rho = 1.000\nCircular controlled evidence is not external validity\nHuman agreement and counterfactual replay are required",
            PALETTE["purple"],
            PALETTE["purple_strong"],
        ),
        (
            (70, 660, 910, 900),
            "RQ3  CONTROLLED RESULT ONLY",
            "Injected-bloat ratio under designed fixtures\nTool 0.500  >  Retrieval 0.487  >  Memory 0.468\nNatural source ranking requires Study B",
            PALETTE["orange"],
            PALETTE["orange_strong"],
        ),
        (
            (990, 660, 1830, 900),
            "RQ4  STUDY A DEGRADATION RISK",
            "Token reduction: 48.85%  [42.67%, 55.31%]\nTask-success difference: -6.11 pp  [-12.22, -0.56]\nNon-inferiority is not established; Study C comparison pending",
            PALETTE["red"],
            PALETTE["red_strong"],
        ),
    ]
    for xy, title, body, fill, accent in rq_boxes:
        canvas.box(
            xy,
            title,
            body,
            fill=fill,
            accent=accent,
            title_size=26,
            body_size=22,
        )

    canvas.rect(
        (70, 970, 1830, 1115),
        fill=PALETTE["gold"],
        stroke=PALETTE["gold_strong"],
        radius=8,
    )
    canvas.text(
        (950, 1020),
        "Engineering conclusion",
        size=25,
        bold=True,
        color=PALETTE["gold_strong"],
    )
    canvas.text(
        (950, 1065),
        "Runtime auditing makes context and interventions traceable; independent labels and utility tests determine what counts as removable bloat.",
        size=22,
        bold=True,
        max_width=1640,
    )
    canvas.text(
        (950, 1150),
        "Draft scope: Study A is frozen; registered Study B/C real-model evidence and blind annotation remain pending.",
        size=19,
        color=PALETTE["muted"],
        max_width=1700,
    )
    canvas.save(output_dir / "figure_7_1_graphical_abstract")


def build(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    research_overview(output_dir)
    experiment_workflow(output_dir)
    graphical_abstract(output_dir)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    build(args.output_dir)
    print(f"Built core thesis figures in: {args.output_dir}")


if __name__ == "__main__":
    main()
