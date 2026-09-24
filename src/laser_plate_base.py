#!/usr/bin/env python3
"""Generate four finger-jointed side panels as a laser-cutting SVG.

Width and depth are the finished OUTSIDE dimensions of the assembled frame.
All dimensions are in millimetres.  Red paths are cut lines; blue text is an
optional engraving/annotation layer and can be hidden with --no-labels.

The joints need no wedges or separate hardware: alternating fingers on the
front/back panels interlock with the complementary fingers on the side panels.
"""

from __future__ import annotations

import argparse
import html
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Panel:
    name: str
    length: float
    tabs_on_even_bands: bool


def fmt(value: float) -> str:
    """Compact, deterministic SVG number formatting."""
    return f"{value:.4f}".rstrip("0").rstrip(".")


def boundary_points(
    length: float,
    height: float,
    thickness: float,
    fingers: int,
    tabs_on_even_bands: bool,
    clearance: float,
    right: bool,
) -> list[tuple[float, float]]:
    """Return one stepped vertical edge, ordered from top to bottom.

    A positive clearance shortens every internal finger in the vertical
    direction.  Its complementary gap therefore becomes larger by the same
    amount, producing a looser press fit without changing the panel envelope.
    """
    inner = length - thickness if right else thickness
    outer = length if right else 0.0
    band = height / fingers

    # Each item is (start_y, end_y) for a protruding finger.
    intervals: list[tuple[float, float]] = []
    for i in range(fingers):
        active = (i % 2 == 0) == tabs_on_even_bands
        if not active:
            continue
        start = i * band
        end = (i + 1) * band
        # Preserve the outer top/bottom corners; shrink only internal edges.
        if start > 0:
            start += clearance / 2
        if end < height:
            end -= clearance / 2
        intervals.append((start, end))

    events: list[tuple[float, bool]] = []
    starts_at_top = False
    for start, end in intervals:
        if start == 0:
            starts_at_top = True
        else:
            events.append((start, True))
        if end < height:
            events.append((end, False))

    state = starts_at_top
    points = [(outer if state else inner, 0.0)]
    for y, new_state in sorted(events):
        old_x = outer if state else inner
        new_x = outer if new_state else inner
        points.extend(((old_x, y), (new_x, y)))
        state = new_state
    points.append((outer if state else inner, height))
    return points


def panel_outline(
    length: float,
    height: float,
    thickness: float,
    fingers: int,
    tabs_on_even_bands: bool,
    clearance: float,
) -> list[tuple[float, float]]:
    """Create one closed, clockwise polygon for a panel."""
    right = boundary_points(
        length, height, thickness, fingers, tabs_on_even_bands,
        clearance, right=True
    )
    left = boundary_points(
        length, height, thickness, fingers, tabs_on_even_bands,
        clearance, right=False
    )
    return right + list(reversed(left))


def path_data(points: list[tuple[float, float]], dx: float, dy: float) -> str:
    commands = [f"M {fmt(points[0][0] + dx)} {fmt(points[0][1] + dy)}"]
    commands.extend(
        f"L {fmt(x + dx)} {fmt(y + dy)}" for x, y in points[1:]
    )
    commands.append("Z")
    return " ".join(commands)


def build_svg(args: argparse.Namespace) -> str:
    panels = [
        Panel("Front", args.width, True),
        Panel("Back", args.width, True),
        Panel("Left", args.depth, False),
        Panel("Right", args.depth, False),
    ]

    margin = args.margin
    gap = args.gap
    canvas_width = max(args.width, args.depth) + 2 * margin
    canvas_height = 4 * args.height + 3 * gap + 2 * margin

    svg: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{fmt(canvas_width)}mm" height="{fmt(canvas_height)}mm" '
        f'viewBox="0 0 {fmt(canvas_width)} {fmt(canvas_height)}">',
        "  <title>Four-panel press-fit plate base</title>",
        "  <desc>Dimensions are millimetres. Red paths are through-cuts; "
        "blue text is engraving.</desc>",
        f'  <g id="cut" fill="none" stroke="#ff0000" '
        f'stroke-width="{fmt(args.line_width)}" vector-effect="non-scaling-stroke" '
        f'stroke-linejoin="miter">',
    ]

    label_rows: list[tuple[str, float, float]] = []
    y = margin
    for panel in panels:
        x = (canvas_width - panel.length) / 2
        outline = panel_outline(
            panel.length,
            args.height,
            args.thickness,
            args.fingers,
            panel.tabs_on_even_bands,
            args.clearance,
        )
        svg.append(
            f'    <path id="{panel.name.lower()}-panel" '
            f'd="{path_data(outline, x, y)}" />'
        )
        label_rows.append((panel.name, canvas_width / 2, y + args.height / 2))
        y += args.height + gap
    svg.append("  </g>")

    if args.labels:
        svg.append(
            '  <g id="engrave" fill="#0000ff" stroke="none" '
            'font-family="sans-serif" text-anchor="middle">'
        )
        for name, x, y in label_rows:
            label = html.escape(
                f"{name}  {args.width:g}×{args.depth:g}×{args.height:g} mm, "
                f"t={args.thickness:g}"
            )
            svg.append(
                f'    <text x="{fmt(x)}" y="{fmt(y)}" '
                f'font-size="{fmt(args.label_size)}">{label}</text>'
            )
        svg.append("  </g>")

    metadata = (
        f"outside_width={args.width}; outside_depth={args.depth}; "
        f"height={args.height}; material_thickness={args.thickness}; "
        f"finger_count={args.fingers}; fit_clearance={args.clearance}; "
        f"expected_laser_kerf={args.kerf}"
    )
    svg.append(f"  <!-- {metadata} -->")
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def positive(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def nonnegative(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Draw four finger-jointed side panels for laser cutting."
    )
    parser.add_argument("--width", type=positive, required=True,
                        help="assembled outside width in mm")
    parser.add_argument("--depth", type=positive, required=True,
                        help="assembled outside depth in mm")
    parser.add_argument("--height", type=positive, required=True,
                        help="panel height in mm")
    parser.add_argument("--thickness", type=positive, required=True,
                        help="measured material thickness in mm")
    parser.add_argument("--fingers", type=int, default=5,
                        help="odd number of vertical finger bands (default: 5)")
    parser.add_argument("--clearance", type=nonnegative, default=0.10,
                        help="extra joint clearance in mm (default: 0.10)")
    parser.add_argument("--kerf", type=nonnegative, default=0.15,
                        help="expected kerf, recorded as metadata (default: 0.15)")
    parser.add_argument("--gap", type=nonnegative, default=8.0,
                        help="layout gap between panels (default: 8)")
    parser.add_argument("--margin", type=nonnegative, default=5.0,
                        help="SVG sheet margin (default: 5)")
    parser.add_argument("--line-width", type=positive, default=0.10,
                        help="cut-line display width (default: 0.10)")
    parser.add_argument("--label-size", type=positive, default=3.0,
                        help="engraved label size (default: 3)")
    parser.add_argument("--no-labels", dest="labels", action="store_false",
                        help="omit the blue engraving labels")
    parser.add_argument("-o", "--output", type=Path, default=Path("plate_base.svg"),
                        help="output SVG path (default: plate_base.svg)")
    args = parser.parse_args()

    if args.fingers < 3 or args.fingers % 2 == 0:
        parser.error("--fingers must be an odd integer of at least 3")
    if args.width <= 2 * args.thickness:
        parser.error("--width must be greater than twice --thickness")
    if args.depth <= 2 * args.thickness:
        parser.error("--depth must be greater than twice --thickness")
    if args.height / args.fingers <= args.clearance:
        parser.error("finger bands are too short for the requested clearance")
    return args


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_svg(args), encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")


if __name__ == "__main__":
    main()
