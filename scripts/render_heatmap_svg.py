#!/usr/bin/env python3
"""
Render data/contributions.json (produced by fetch_contributions.py) as a proper
GitHub-style contribution heatmap SVG: a grid of rounded, colored BOXES in the
classic 53-week x 7-day calendar.

Reveal animation: a little jet flies left -> right underneath the grid. Every
time it passes beneath a column that has a real contribution, it fires a
tracer shot up at each active cell in that column; on impact there's a small
explosion burst and the cell "appears" in its real color right as the flash
fades. Empty (no-contribution) tiles are just always-visible background --
they're never targeted. After the plane's one pass, a soft green sheen keeps
sweeping the grid forever so it still feels alive.

Run by .github/workflows/update-profile-art.yml after fetch_contributions.py.
"""
import datetime
import json
import math
import os

HERE = os.path.dirname(__file__)
IN_PATH = os.path.join(HERE, "..", "data", "contributions.json")
OUT_PATH = os.path.join(HERE, "..", "contrib-heatmap.svg")

# GitHub-ish green ramp: empty -> brightest. Level 5 is a brighter neon top end.
PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353", "#69f0a0"]

CELL = 12
GAP = 3
STEP = CELL + GAP
PAD = 22
LEFT_LABEL_W = 30
TOP_LABEL_H = 20
TITLEBAR_H = 30
PLANE_LANE = 34  # extra vertical space below the grid for the plane to fly through

BG = "#0a0e14"
BG2 = "#0d1420"
FRAME = "#1f6feb"
MUTED = "#7d8590"
TEXT = "#e6edf3"
ACCENT = "#22d3ee"
GREEN = "#39d353"
GOLD = "#f2cc60"

# plane-bomb reveal timing (one-shot, plays once on load then freezes)
FLIGHT = 7.0        # seconds for the plane to cross the whole grid
TRAVEL = 0.16       # seconds for a tracer shot to travel from plane to cell
EXPLODE = 0.4       # seconds for the impact flash / cell reveal
ROW_STAGGER = 0.12  # extra delay between shots fired at the same column


def level_for(count):
    if count == 0:
        return 0
    if count <= 5:
        return 1
    if count <= 15:
        return 2
    if count <= 30:
        return 3
    if count <= 50:
        return 4
    return 5


def build_grid(days):
    first = datetime.date.fromisoformat(days[0]["date"])
    lead_pad = (first.weekday() + 1) % 7  # sunday=0
    grid = []
    col = [None] * lead_pad
    for d in days:
        date = datetime.date.fromisoformat(d["date"])
        weekday = (date.weekday() + 1) % 7
        while len(col) < weekday:
            col.append(None)
        col.append((d["date"], d["count"], level_for(d["count"])))
        if len(col) == 7:
            grid.append(col)
            col = []
    if col:
        while len(col) < 7:
            col.append(None)
        grid.append(col)
    return grid


def render(data):
    days = data["days"]
    grid = build_grid(days)
    n_cols = len(grid)
    art_w = n_cols * STEP
    art_h = 7 * STEP

    month_labels = []
    seen_months = set()
    for ci, column in enumerate(grid):
        for cell in column:
            if cell is None:
                continue
            date = datetime.date.fromisoformat(cell[0])
            key = (date.year, date.month)
            if key not in seen_months and date.day <= 7:
                seen_months.add(key)
                month_labels.append((ci, date.strftime("%b")))
            break

    canvas_w = PAD + LEFT_LABEL_W + art_w + PAD
    stats_h = 88
    grid_top = TITLEBAR_H + TOP_LABEL_H
    grid_left = PAD + LEFT_LABEL_W
    canvas_h = grid_top + art_h + PLANE_LANE + stats_h + PAD

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" '
        f'viewBox="0 0 {canvas_w} {canvas_h}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">',
        '<defs>'
        f'<linearGradient id="hbg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/></linearGradient>'
        '</defs>',
        f'<rect width="{canvas_w}" height="{canvas_h}" rx="12" fill="url(#hbg)"/>',
        f'<rect x="0.5" y="0.5" width="{canvas_w-1}" height="{canvas_h-1}" rx="12" '
        f'fill="none" stroke="{FRAME}" stroke-width="1" stroke-opacity="0.55"/>',
        f'<line x1="0" y1="{TITLEBAR_H}" x2="{canvas_w}" y2="{TITLEBAR_H}" stroke="{FRAME}" stroke-opacity="0.35"/>',
    ]
    for i, dotcol in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        parts.append(f'<circle cx="{PAD + i*16}" cy="{TITLEBAR_H/2}" r="5" fill="{dotcol}"/>')
    parts.append(f'<text x="{canvas_w/2}" y="{TITLEBAR_H/2 + 4}" fill="{MUTED}" font-size="12" '
                 f'text-anchor="middle">avi@github: ~/contributions --graph</text>')

    for ci, label in month_labels:
        x = grid_left + ci * STEP
        parts.append(f'<text x="{x}" y="{TITLEBAR_H + 14}" fill="{MUTED}" font-size="10">{label}</text>')

    for wi, wname in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        y = grid_top + wi * STEP + CELL * 0.78
        parts.append(f'<text x="{PAD}" y="{y:.1f}" fill="{MUTED}" font-size="9">{wname}</text>')

    # ---- work out plane-flight timing and per-cell impact times ----
    plane_y = grid_top + art_h + PLANE_LANE / 2
    plane_x_start = grid_left - 26
    plane_x_end = grid_left + art_w + 26

    def frame_for_x(x):
        return (x - plane_x_start) / (plane_x_end - plane_x_start) * FLIGHT

    active_by_col = {}
    for ci, column in enumerate(grid):
        for ri, cell in enumerate(column):
            if cell is None:
                continue
            _, count, lvl = cell
            if lvl >= 1:
                active_by_col.setdefault(ci, []).append((ri, lvl))

    impact = {}  # (ci,ri) -> impact time in seconds
    for ci, rows in active_by_col.items():
        col_center_x = grid_left + ci * STEP + CELL / 2
        base_t = frame_for_x(col_center_x)
        rows.sort()
        for k, (ri, lvl) in enumerate(rows):
            impact[(ci, ri)] = base_t + k * ROW_STAGGER

    last_impact = max(impact.values()) if impact else 0.0
    reveal_end = last_impact + EXPLODE + 0.5

    # ---- base cells: always-visible background tiles ----
    for ci, column in enumerate(grid):
        gx = grid_left + ci * STEP
        for ri, cell in enumerate(column):
            if cell is None:
                continue
            date_s, count, lvl = cell
            gy = grid_top + ri * STEP
            plural = "s" if count != 1 else ""
            base_color = PALETTE[0] if lvl >= 1 else PALETTE[lvl]
            parts.append(
                f'<rect x="{gx}" y="{gy}" width="{CELL}" height="{CELL}" rx="2.5" fill="{base_color}">'
                f'<title>{date_s}: {count} contribution{plural}</title></rect>'
            )

    # ---- reveal overlay + impact bursts + tracer shots for active cells ----
    for (ci, ri), t in impact.items():
        column = grid[ci]
        _, count, lvl = column[ri]
        gx = grid_left + ci * STEP
        gy = grid_top + ri * STEP
        cx, cy = gx + CELL / 2, gy + CELL / 2

        # cell reveal: fades from base color to its real level color at impact
        parts.append(
            f'<rect x="{gx}" y="{gy}" width="{CELL}" height="{CELL}" rx="2.5" fill="{PALETTE[lvl]}" opacity="0">'
            f'<animate attributeName="opacity" from="0" to="1" begin="{t:.3f}s" dur="{EXPLODE:.2f}s" fill="freeze"/>'
            f'</rect>'
        )

        # impact burst: flash core + radiating spikes, timed to the same moment
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="1" fill="#fff0c8">'
            f'<animate attributeName="r" from="1" to="9" begin="{t:.3f}s" dur="{EXPLODE:.2f}s" fill="freeze"/>'
            f'<animate attributeName="opacity" from="1" to="0" begin="{t:.3f}s" dur="{EXPLODE:.2f}s" fill="freeze"/>'
            f'</circle>'
        )
        for si in range(6):
            ang = si * (2 * math.pi / 6)
            x2 = cx + math.cos(ang) * 10
            y2 = cy + math.sin(ang) * 10
            parts.append(
                f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="#ffb066" stroke-width="1.4" opacity="0">'
                f'<animate attributeName="opacity" values="0;1;0" begin="{t:.3f}s" dur="{EXPLODE:.2f}s" fill="freeze"/>'
                f'</line>'
            )

        # tracer shot: travels from the plane up to this cell just before impact
        shot_begin = max(0.0, t - TRAVEL)
        parts.append(
            f'<circle r="1.6" fill="#fff2c8" opacity="0">'
            f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.05;0.85;1" '
            f'begin="{shot_begin:.3f}s" dur="{TRAVEL:.2f}s" fill="freeze"/>'
            f'<animate attributeName="cx" from="{cx:.1f}" to="{cx:.1f}" '
            f'begin="{shot_begin:.3f}s" dur="{TRAVEL:.2f}s" fill="freeze"/>'
            f'<animate attributeName="cy" from="{plane_y:.1f}" to="{cy:.1f}" '
            f'begin="{shot_begin:.3f}s" dur="{TRAVEL:.2f}s" fill="freeze" '
            f'calcMode="spline" keySplines="0.3 0 0.7 1"/>'
            f'</circle>'
        )

    # ---- the plane itself: simple jet shape, flies once left -> right ----
    parts.append(f'<g transform="translate({plane_x_start},{plane_y})">')
    parts.append(
        f'<animateTransform attributeName="transform" type="translate" additive="sum" '
        f'from="0 0" to="{plane_x_end - plane_x_start:.1f} 0" begin="0.05s" dur="{FLIGHT:.2f}s" fill="freeze"/>'
    )
    parts.append(
        '<polygon points="-2,0 -10,9 -4,2" fill="#78828c"/>'
        '<polygon points="-2,0 -10,-9 -4,-2" fill="#78828c"/>'
        '<polygon points="-9,0 -15,-6 -11,0" fill="#78828c"/>'
        '<ellipse cx="0" cy="0" rx="10" ry="3.5" fill="#d2d7de"/>'
        '<polygon points="8,-2 14,0 8,2" fill="#f0f4f8"/>'
        '<ellipse cx="2" cy="0" rx="4" ry="1.8" fill="#4682d2"/>'
        '<polygon points="-10,-1.4 -16,0 -10,1.4" fill="#ffb066"/>'
    )
    parts.append('</g>')

    # legend + stats footer
    art_bottom = grid_top + art_h + PLANE_LANE
    leg_y = art_bottom + 6
    leg_x = canvas_w - PAD - (len(PALETTE) * (CELL - 1) + 70)
    parts.append(f'<text x="{leg_x}" y="{leg_y + CELL*0.8:.1f}" fill="{MUTED}" font-size="10" text-anchor="end">Less</text>')
    lx = leg_x + 8
    for lvl, color in enumerate(PALETTE):
        parts.append(f'<rect x="{lx}" y="{leg_y}" width="{CELL-1}" height="{CELL-1}" rx="2.2" fill="{color}"/>')
        lx += CELL
    parts.append(f'<text x="{lx + 4}" y="{leg_y + CELL*0.8:.1f}" fill="{MUTED}" font-size="10">More</text>')

    sep_y = leg_y + CELL + 14
    parts.append(f'<line x1="0" y1="{sep_y}" x2="{canvas_w}" y2="{sep_y}" stroke="{FRAME}" stroke-opacity="0.25"/>')

    # continuous scanning sheen across the grid -- starts once the plane's pass
    # (and every impact) has finished, then loops forever so the graph still
    # feels "alive" long after the one-shot reveal is done
    sweep_w = 90
    parts.append(
        '<defs><linearGradient id="sweep" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#39d353" stop-opacity="0"/>'
        '<stop offset="0.5" stop-color="#69f0a0" stop-opacity="0.28"/>'
        '<stop offset="1" stop-color="#39d353" stop-opacity="0"/>'
        '</linearGradient></defs>'
    )
    parts.append(
        f'<clipPath id="gridclip"><rect x="{grid_left}" y="{grid_top}" width="{art_w}" height="{art_h}"/></clipPath>'
    )
    parts.append(
        f'<g clip-path="url(#gridclip)">'
        f'<rect x="{grid_left - sweep_w}" y="{grid_top}" width="{sweep_w}" height="{art_h}" fill="url(#sweep)">'
        f'<animate attributeName="x" from="{grid_left - sweep_w}" to="{grid_left + art_w}" '
        f'begin="{reveal_end:.2f}s" dur="3.2s" repeatCount="indefinite"/>'
        f'</rect></g>'
    )

    cs = data["current_streak"]["length"]
    ls = data["longest_streak"]["length"]
    total = data["total_contributions"]
    best = data["best_day"]
    rng = data["range"]

    ly = sep_y + 24
    parts.append(f'<text x="{PAD}" y="{ly}" font-size="13" fill="{GREEN}">'
                 f'<tspan font-weight="700">{total:,}</tspan>'
                 f'<tspan fill="{MUTED}"> contributions in the last year</tspan></text>')
    parts.append(f'<text x="{canvas_w - PAD}" y="{ly}" font-size="12" fill="{MUTED}" text-anchor="end">'
                 f'{rng["start"]} &#8594; {rng["end"]}</text>')
    ly += 24
    parts.append(f'<text x="{PAD}" y="{ly}" font-size="13" fill="{MUTED}">current streak '
                 f'<tspan fill="{ACCENT}" font-weight="700">{cs} days</tspan>'
                 f'<tspan fill="{MUTED}">   &#183;   longest </tspan>'
                 f'<tspan fill="{ACCENT}" font-weight="700">{ls} days</tspan></text>')
    parts.append(f'<text x="{canvas_w - PAD}" y="{ly}" font-size="12" fill="{MUTED}" text-anchor="end">'
                 f'best day <tspan fill="{GOLD}" font-weight="700">{best["count"]}</tspan> on {best["date"]}</text>')

    parts.append("</svg>")
    return "".join(parts)


if __name__ == "__main__":
    data = json.load(open(IN_PATH))
    svg = render(data)
    with open(OUT_PATH, "w") as f:
        f.write(svg)
    print(f"wrote {OUT_PATH} ({len(svg)} bytes)")
