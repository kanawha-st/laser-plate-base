#!/usr/bin/env python3
"""Draw a four-panel tab-and-slot frame for laser cutting.

Front/back panels have straight tabs. Left/right panels have closed through
slots. The default tabs have a downward hook: insert them 5 mm high, then slide
the board down so the hook catches behind the lower slot edge. A non-locking
straight-tab mode is also available.
All dimensions are millimetres; width/depth are assembled outside dimensions.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path


def f(n: float) -> str:
    return f"{n:.4f}".rstrip("0").rstrip(".")


def intervals(height: float, count: int, tab_height: float, shifted: bool):
    pitch = height / (count + 1)
    offset = pitch / 3 if shifted else 0.0
    result = []
    for i in range(count):
        center = (i + 1) * pitch + offset
        result.append((center - tab_height / 2, center + tab_height / 2))
    return result


def edge_points(length, height, thickness, tabs, right):
    inner = length - thickness if right else thickness
    outer = length if right else 0.0
    events = []
    for start, end in tabs:
        events.extend(((start, True), (end, False)))
    state = False
    points = [(inner, 0.0)]
    for y, new_state in sorted(events):
        old_x = outer if state else inner
        new_x = outer if new_state else inner
        points.extend(((old_x, y), (new_x, y)))
        state = new_state
    points.append((inner, height))
    return points


def tabbed_outline(length, height, thickness, left_tabs, right_tabs):
    right = edge_points(length, height, thickness, right_tabs, True)
    left = edge_points(length, height, thickness, left_tabs, False)
    return right + list(reversed(left))


def rectangle(x, y, width, height):
    return [(x, y), (x + width, y), (x + width, y + height),
            (x, y + height)]


def union_outline(rectangles):
    """Return the outer contour of an orthogonal union of rectangles."""
    xs = sorted({x for rx, _, rw, _ in rectangles for x in (rx, rx + rw)})
    ys = sorted({y for _, ry, _, rh in rectangles for y in (ry, ry + rh)})
    filled = set()
    for ix in range(len(xs) - 1):
        for iy in range(len(ys) - 1):
            mx = (xs[ix] + xs[ix + 1]) / 2
            my = (ys[iy] + ys[iy + 1]) / 2
            if any(rx < mx < rx + rw and ry < my < ry + rh
                   for rx, ry, rw, rh in rectangles):
                filled.add((ix, iy))

    edges = {}
    for ix, iy in filled:
        x0, x1 = xs[ix], xs[ix + 1]
        y0, y1 = ys[iy], ys[iy + 1]
        candidates = (
            ((ix, iy - 1), (x0, y0), (x1, y0)),
            ((ix + 1, iy), (x1, y0), (x1, y1)),
            ((ix, iy + 1), (x1, y1), (x0, y1)),
            ((ix - 1, iy), (x0, y1), (x0, y0)),
        )
        for neighbour, start, end in candidates:
            if neighbour not in filled:
                edges[start] = end

    start = min(edges, key=lambda point: (point[1], point[0]))
    contour = [start]
    current = start
    while True:
        current = edges[current]
        if current == start:
            break
        contour.append(current)
    # Remove redundant points on straight runs.
    simplified = []
    for point in contour:
        simplified.append(point)
        while len(simplified) >= 3:
            a, b, c = simplified[-3:]
            if (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1]):
                simplified.pop(-2)
            else:
                break
    return simplified


def hooked_outline(length, height, thickness, left_tabs, right_tabs,
                   overhang, lock_drop):
    """Panel outline with downward hooks that catch below the entry slots."""
    rectangles = [(thickness, 0.0, length - 2 * thickness, height)]
    for side, tabs in (("left", left_tabs), ("right", right_tabs)):
        for start, end in tabs:
            head_height = end - start
            neck_height = head_height - lock_drop
            if side == "left":
                rectangles.append((-overhang, start,
                                   thickness + overhang, neck_height))
                rectangles.append((-overhang, start, overhang, head_height))
            else:
                rectangles.append((length - thickness, start,
                                   thickness + overhang, neck_height))
                rectangles.append((length, start, overhang, head_height))
    return union_outline(rectangles)


def path(points, dx=0.0, dy=0.0):
    commands = [f"M {f(points[0][0] + dx)} {f(points[0][1] + dy)}"]
    commands += [f"L {f(x + dx)} {f(y + dy)}" for x, y in points[1:]]
    return " ".join(commands) + " Z"


def rotate_side(points, panel_height):
    """Rotate a depth×height side panel 90 degrees clockwise."""
    return [(panel_height - y, x) for x, y in points]


def can_nest(a):
    """Check that the nested cuts leave useful bridges of side-panel material."""
    inner_width = a.width + (2 * a.hook_overhang if a.joint == "hook" else 0)
    horizontal_bridge = (a.height - inner_width) / 2
    vertical_margin = (a.depth - a.height) / 2
    slot_end = a.edge_setback + a.thickness + a.clearance / 2
    return (horizontal_bridge >= a.min_bridge and
            vertical_margin - slot_end >= a.min_bridge)


def create_svg(a):
    tab_height = a.tab_height or a.height / (2 * a.tabs + 1)
    neck_height = (tab_height - a.lock_drop
                   if a.joint == "hook" else tab_height)
    set_a = intervals(a.height, a.tabs, tab_height, False)
    set_b = intervals(a.height, a.tabs, tab_height, a.stagger)
    layout = "nested" if a.layout == "auto" and can_nest(a) else a.layout
    if layout == "auto":
        layout = "stacked"
    if layout == "nested" and not can_nest(a):
        raise ValueError(
            "nested layout does not fit safely; reduce width/height, reduce "
            "--min-bridge, or use --layout stacked"
        )
    if layout == "nested":
        sheet_w = 2 * a.height + a.gap + 2 * a.margin
        sheet_h = a.depth + 2 * a.margin
    else:
        tabbed_width = a.width + (2 * a.hook_overhang
                                  if a.joint == "hook" else 0)
        sheet_w = max(tabbed_width, a.depth) + 2 * a.margin
        sheet_h = 4 * a.height + 3 * a.gap + 2 * a.margin
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(sheet_w)}mm" '
        f'height="{f(sheet_h)}mm" viewBox="0 0 {f(sheet_w)} {f(sheet_h)}">',
        '  <title>Four-panel loose tab-and-slot plate base</title>',
        '  <desc>Red paths are through-cuts. Blue text is optional engraving.</desc>',
        f'  <g id="cut" fill="none" stroke="#ff0000" '
        f'stroke-width="{f(a.line_width)}" vector-effect="non-scaling-stroke">',
    ]
    labels = []
    slot_w = a.thickness + a.clearance
    slot_h = tab_height + a.clearance
    front_center = a.edge_setback + a.thickness / 2
    back_center = a.depth - a.edge_setback - a.thickness / 2

    if layout == "nested":
        pairs = [
            ("Left", set_a, set_b, "Front", set_a, set_b),
            ("Right", set_b, set_a, "Back", set_b, set_a),
        ]
        for index, (side_name, front_pattern, back_pattern,
                    inner_name, left_pattern, right_pattern) in enumerate(pairs):
            x = a.margin + index * (a.height + a.gap)
            y = a.margin
            side_outline = rotate_side(
                rectangle(0, 0, a.depth, a.height), a.height
            )
            lines.append(
                f'    <path id="{side_name.lower()}-outline" '
                f'd="{path(side_outline, x, y)}"/>'
            )
            for edge_name, center_x, pattern in (
                ("front", front_center, front_pattern),
                ("back", back_center, back_pattern),
            ):
                for number, (start, end) in enumerate(pattern, 1):
                    center_y = (start + end) / 2
                    if a.joint == "hook":
                        # The board is inserted 5 mm high, then moved down.
                        # In the final position the narrow neck remains in the
                        # slot and the lower hook catches behind its bottom edge.
                        hole = rectangle(
                            center_x - slot_w / 2,
                            start - a.lock_drop - a.clearance / 2,
                            slot_w, tab_height + a.clearance
                        )
                    else:
                        hole = rectangle(center_x - slot_w / 2,
                                         center_y - slot_h / 2,
                                         slot_w, slot_h)
                    hole = rotate_side(hole, a.height)
                    lines.append(
                        f'    <path id="{side_name.lower()}-{edge_name}-slot-{number}" '
                        f'd="{path(hole, x, y)}"/>'
                    )

            if a.joint == "hook":
                inner = hooked_outline(
                    a.width, a.height, a.thickness, left_pattern, right_pattern,
                    a.hook_overhang, a.lock_drop
                )
            else:
                inner = tabbed_outline(
                    a.width, a.height, a.thickness, left_pattern, right_pattern
                )
            inner_x = x + (a.height - a.width) / 2
            inner_y = y + (a.depth - a.height) / 2
            lines.append(
                f'    <path id="{inner_name.lower()}-outline" '
                f'd="{path(inner, inner_x, inner_y)}"/>'
            )
            labels.append((inner_name, inner_x + a.width / 2,
                           inner_y + a.height / 2, 0))
            labels.append((side_name, x + a.label_size,
                           y + a.depth / 2, -90))
    else:
        panels = [
            ("Front", a.width, "tab", set_a, set_b),
            ("Back",  a.width, "tab", set_b, set_a),
            ("Left",  a.depth, "slot", set_a, set_b),
            ("Right", a.depth, "slot", set_b, set_a),
        ]
        y = a.margin
        for name, length, kind, front_pattern, back_pattern in panels:
            x = (sheet_w - length) / 2
            if kind == "tab" and a.joint == "hook":
                outline = hooked_outline(
                    length, a.height, a.thickness, front_pattern, back_pattern,
                    a.hook_overhang, a.lock_drop
                )
            elif kind == "tab":
                outline = tabbed_outline(length, a.height, a.thickness,
                                         front_pattern, back_pattern)
            else:
                outline = rectangle(0, 0, length, a.height)
            lines.append(
                f'    <path id="{name.lower()}-outline" d="{path(outline, x, y)}"/>'
            )
            if kind == "slot":
                for edge_name, center_x, pattern in (
                    ("front", front_center, front_pattern),
                    ("back", back_center, back_pattern),
                ):
                    for number, (start, end) in enumerate(pattern, 1):
                        center_y = (start + end) / 2
                        if a.joint == "hook":
                            hole = rectangle(
                                center_x - slot_w / 2,
                                start - a.lock_drop - a.clearance / 2,
                                slot_w, tab_height + a.clearance
                            )
                        else:
                            hole = rectangle(center_x - slot_w / 2,
                                             center_y - slot_h / 2,
                                             slot_w, slot_h)
                        lines.append(
                            f'    <path id="{name.lower()}-{edge_name}-slot-{number}" '
                            f'd="{path(hole, x, y)}"/>'
                        )
            labels.append((name, sheet_w / 2, y + a.height / 2, 0))
            y += a.height + a.gap
    lines.append("  </g>")

    if a.labels:
        lines.append('  <g id="engrave" fill="#0000ff" stroke="none" '
                     'font-family="sans-serif" text-anchor="middle">')
        for name, x, y, rotation in labels:
            text = html.escape(
                f"{name}  {a.width:g}×{a.depth:g}×{a.height:g} mm, t={a.thickness:g}"
            )
            transform = (f' transform="rotate({rotation} {f(x)} {f(y)})"'
                         if rotation else "")
            lines.append(f'    <text x="{f(x)}" y="{f(y)}"{transform} '
                         f'font-size="{f(a.label_size)}">{text}</text>')
        lines.append("  </g>")
    lines.append(
        f"  <!-- clearance={a.clearance}; expected_kerf={a.kerf}; "
        f"edge_setback={a.edge_setback}; tab_height={tab_height}; "
        f"layout={layout}; min_bridge={a.min_bridge}; joint={a.joint}; "
        f"hook_overhang={a.hook_overhang}; lock_drop={a.lock_drop}; "
        f"neck_height={neck_height} -->"
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def positive(s):
    n = float(s)
    if n <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return n


def nonnegative(s):
    n = float(s)
    if n < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return n


def arguments():
    p = argparse.ArgumentParser(description="Loose tab-and-slot frame SVG generator")
    p.add_argument("--width", required=True, type=positive)
    p.add_argument("--depth", required=True, type=positive)
    p.add_argument("--height", required=True, type=positive)
    p.add_argument("--thickness", required=True, type=positive)
    p.add_argument("--tabs", type=int, default=3,
                   help="tabs at each corner (default: 3)")
    p.add_argument("--tab-height", type=positive,
                   help="tab height; default is calculated from panel height")
    p.add_argument("--clearance", type=nonnegative, default=0.20,
                   help="extra slot width/height for loose assembly (default: 0.20)")
    p.add_argument("--edge-setback", type=positive,
                   help="front/back inset from depth edges (default: thickness)")
    p.add_argument("--kerf", type=nonnegative, default=0.15)
    p.add_argument("--joint", choices=("hook", "straight"), default="hook",
                   help="hook locks by downward sliding; straight pulls apart")
    p.add_argument("--hook-overhang", type=positive, default=5.0,
                   help="hook projection beyond side panel in mm (default: 5)")
    p.add_argument("--lock-drop", type=positive, default=5.0,
                   help="downward locking movement/hook depth (default: 5)")
    p.add_argument("--layout", choices=("auto", "nested", "stacked"),
                   default="auto", help="panel layout (default: auto)")
    p.add_argument("--min-bridge", type=positive,
                   help="minimum material around nested panel (default: 2× thickness)")
    p.add_argument("--no-stagger", dest="stagger", action="store_false",
                   help="use matching vertical positions at every corner")
    p.add_argument("--no-labels", dest="labels", action="store_false")
    p.add_argument("--gap", type=nonnegative, default=8.0)
    p.add_argument("--margin", type=nonnegative, default=5.0)
    p.add_argument("--line-width", type=positive, default=0.10)
    p.add_argument("--label-size", type=positive, default=3.0)
    p.add_argument("-o", "--output", type=Path, default=Path("slot_insert_base.svg"))
    a = p.parse_args()
    a.edge_setback = a.edge_setback or a.thickness
    a.min_bridge = a.min_bridge or 2 * a.thickness
    tab_h = a.tab_height or a.height / (2 * a.tabs + 1)
    if a.tabs < 1:
        p.error("--tabs must be at least 1")
    if a.joint == "hook" and a.lock_drop >= tab_h:
        p.error("--lock-drop must be smaller than the tab height")
    if min(a.width, a.depth) <= 2 * a.thickness:
        p.error("width and depth must exceed twice the thickness")
    if a.edge_setback <= a.clearance / 2:
        p.error("edge setback is too small to keep slots closed")
    if 2 * (a.edge_setback + a.thickness) >= a.depth:
        p.error("depth is too small for the selected edge setback")
    last_center = a.tabs * a.height / (a.tabs + 1)
    if a.stagger:
        last_center += a.height / (a.tabs + 1) / 3
    if last_center + tab_h / 2 + a.clearance / 2 >= a.height:
        p.error("tabs do not fit vertically; reduce tab count or tab height")
    first_start = a.height / (a.tabs + 1) - tab_h / 2
    if a.joint == "hook" and first_start - a.lock_drop <= a.clearance / 2:
        p.error("top slot is too close to the edge for the locking movement")
    if a.layout == "nested" and not can_nest(a):
        p.error("nested layout does not leave the requested minimum bridges")
    return a


def main():
    a = arguments()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(create_svg(a), encoding="utf-8")
    print(f"Wrote {a.output.resolve()}")


if __name__ == "__main__":
    main()
