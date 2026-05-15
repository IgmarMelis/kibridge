"""
Simple DRC (Design Rules Check) for KiRouter.

This is a pragmatic checker, not a full DRC engine. KiCad's own DRC is
the source of truth for production. We compute a fast first-pass pass/fail
that catches the most common violations a user would want to see flagged
right after auto-routing, and surfaces them as red markers on the canvas.

Rules implemented:
  - track_width_below_min      : track narrower than design rule minimum
  - via_drill_below_min        : via drill smaller than minimum
  - via_diameter_below_min     : via diameter smaller than minimum
  - track_pad_short            : track endpoint touches a pad on a different net
  - track_track_clearance      : two tracks on the same layer too close, different nets
  - track_outside_board        : track endpoint outside board outline

Each violation is returned as:
  {
    "code":   "track_pad_short",
    "level":  "error" | "warning",
    "msg":    "...",
    "x_mm":   float,    # marker location for the canvas
    "y_mm":   float,
    "layer":  "F.Cu" | "B.Cu" | "any",
    "nets":   ["NET_A", "NET_B"]
  }
"""
from __future__ import annotations

from math import sqrt
from typing import Iterable


def run_drc(board: dict) -> list[dict]:
    rules = (board.get("design_rules") or {}).get("design_settings") or {}
    min_track  = float(rules.get("min_track_width_mm")  or 0.0)
    min_via_d  = float(rules.get("min_via_diameter_mm") or 0.0)
    min_drill  = float(rules.get("min_via_drill_mm")    or 0.0)
    min_clear  = float(rules.get("min_clearance_mm")    or 0.15)

    bbox = (board.get("meta") or {}).get("board_bbox")
    tracks = board.get("tracks") or []
    vias   = board.get("vias")   or []
    fps    = board.get("footprints") or []

    violations: list[dict] = []

    # 1. Track width below minimum
    if min_track > 0:
        for t in tracks:
            if t.get("width_mm", 0) + 1e-9 < min_track:
                mid = _midpoint(t)
                violations.append({
                    "code":  "track_width_below_min",
                    "level": "error",
                    "msg":   (f"Track on net '{t.get('net','')}' is "
                              f"{t.get('width_mm',0)}mm, below "
                              f"min {min_track}mm"),
                    "x_mm":  mid[0],
                    "y_mm":  mid[1],
                    "layer": t.get("layer", "any"),
                    "nets":  [t.get("net", "")],
                })

    # 2. Via diameter / drill below minimum
    for v in vias:
        if min_via_d and v.get("width_mm", 0) + 1e-9 < min_via_d:
            violations.append({
                "code":  "via_diameter_below_min",
                "level": "error",
                "msg":   (f"Via on '{v.get('net','')}' is "
                          f"{v.get('width_mm',0)}mm, below min "
                          f"{min_via_d}mm"),
                "x_mm":  v.get("x_mm", 0),
                "y_mm":  v.get("y_mm", 0),
                "layer": "any",
                "nets":  [v.get("net", "")],
            })
        if min_drill and v.get("drill_mm", 0) + 1e-9 < min_drill:
            violations.append({
                "code":  "via_drill_below_min",
                "level": "error",
                "msg":   (f"Via drill on '{v.get('net','')}' is "
                          f"{v.get('drill_mm',0)}mm, below min "
                          f"{min_drill}mm"),
                "x_mm":  v.get("x_mm", 0),
                "y_mm":  v.get("y_mm", 0),
                "layer": "any",
                "nets":  [v.get("net", "")],
            })

    # 3. Track outside board outline
    if bbox:
        for t in tracks:
            for end in (t.get("start", {}), t.get("end", {})):
                x = end.get("x_mm")
                y = end.get("y_mm")
                if x is None or y is None:
                    continue
                if (x < bbox["x_min"] or x > bbox["x_max"]
                        or y < bbox["y_min"] or y > bbox["y_max"]):
                    violations.append({
                        "code":  "track_outside_board",
                        "level": "error",
                        "msg":   (f"Track on '{t.get('net','')}' has an "
                                  f"endpoint outside the board outline"),
                        "x_mm":  x,
                        "y_mm":  y,
                        "layer": t.get("layer", "any"),
                        "nets":  [t.get("net", "")],
                    })
                    break

    # 4. Track endpoint touches a pad of a DIFFERENT net (short)
    pad_index: list[tuple[float, float, float, float, str]] = []
    for fp in fps:
        for pad in fp.get("pads", []):
            try:
                px = float(pad["x_mm"]); py = float(pad["y_mm"])
            except Exception:
                continue
            sw = (pad.get("size_mm") or [1, 1])[0]
            sh = (pad.get("size_mm") or [1, 1])[1]
            r = max(sw, sh) / 2.0
            pad_index.append((px, py, r, r, pad.get("net", "")))

    for t in tracks:
        net = t.get("net", "")
        for endpoint in (t.get("start", {}), t.get("end", {})):
            ex, ey = endpoint.get("x_mm"), endpoint.get("y_mm")
            if ex is None or ey is None:
                continue
            for (px, py, rx, ry, pad_net) in pad_index:
                if pad_net == net or pad_net == "":
                    continue
                # cheap rectangular hit-test
                if abs(ex - px) < rx and abs(ey - py) < ry:
                    violations.append({
                        "code":  "track_pad_short",
                        "level": "error",
                        "msg":   (f"Track on '{net}' touches a pad on net "
                                  f"'{pad_net}' (short)"),
                        "x_mm":  ex,
                        "y_mm":  ey,
                        "layer": t.get("layer", "any"),
                        "nets":  [net, pad_net],
                    })

    # 5. Track-to-track clearance (different nets, same layer)
    if min_clear > 0:
        # O(n^2) but fine for boards in the hundreds of tracks.
        for i, a in enumerate(tracks):
            for b in tracks[i + 1:]:
                if a.get("layer") != b.get("layer"):
                    continue
                if a.get("net") == b.get("net") and a.get("net"):
                    continue
                d = _segment_distance(
                    a["start"]["x_mm"], a["start"]["y_mm"],
                    a["end"]["x_mm"],   a["end"]["y_mm"],
                    b["start"]["x_mm"], b["start"]["y_mm"],
                    b["end"]["x_mm"],   b["end"]["y_mm"],
                )
                # The clearance is edge-to-edge: subtract half-widths
                edge_d = d - (a.get("width_mm", 0) + b.get("width_mm", 0)) / 2
                if edge_d + 1e-9 < min_clear:
                    mid_a = _midpoint(a)
                    violations.append({
                        "code":  "track_track_clearance",
                        "level": "warning",
                        "msg":   (f"Tracks on '{a.get('net','')}' and "
                                  f"'{b.get('net','')}' too close "
                                  f"(edge dist {edge_d:.3f}mm < "
                                  f"min {min_clear}mm)"),
                        "x_mm":  mid_a[0],
                        "y_mm":  mid_a[1],
                        "layer": a.get("layer", "any"),
                        "nets":  [a.get("net", ""), b.get("net", "")],
                    })

    return violations


# ---- geometry helpers -----------------------------------------------------
def _midpoint(track: dict) -> tuple[float, float]:
    s = track.get("start", {}); e = track.get("end", {})
    return (
        (s.get("x_mm", 0) + e.get("x_mm", 0)) / 2,
        (s.get("y_mm", 0) + e.get("y_mm", 0)) / 2,
    )


def _segment_distance(
    ax1, ay1, ax2, ay2,
    bx1, by1, bx2, by2,
) -> float:
    """Minimum distance between two 2D segments."""
    if _segments_intersect(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
        return 0.0
    return min(
        _point_segment_distance(ax1, ay1, bx1, by1, bx2, by2),
        _point_segment_distance(ax2, ay2, bx1, by1, bx2, by2),
        _point_segment_distance(bx1, by1, ax1, ay1, ax2, ay2),
        _point_segment_distance(bx2, by2, ax1, ay1, ax2, ay2),
    )


def _segments_intersect(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2) -> bool:
    def ccw(ax, ay, bx, by, cx, cy):
        return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)
    return (ccw(ax1, ay1, bx1, by1, bx2, by2)
            != ccw(ax2, ay2, bx1, by1, bx2, by2)
            and ccw(ax1, ay1, ax2, ay2, bx1, by1)
            != ccw(ax1, ay1, ax2, ay2, bx2, by2))


def _point_segment_distance(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return sqrt((px - x1) ** 2 + (py - y1) ** 2)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    nx, ny = x1 + t * dx, y1 + t * dy
    return sqrt((px - nx) ** 2 + (py - ny) ** 2)
