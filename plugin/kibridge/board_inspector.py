"""
KiBridge Inspector - read-only inspection logic.

This module ONLY READS data from a pcbnew BOARD. It must never call any
method that modifies the board (Add/Remove/Delete/Save/etc).

Public API:
    inspect_board(board) -> dict  (JSON-serialisable report)
"""
import os
import re

import pcbnew  # type: ignore

from .version import TOOL_VERSION, SCHEMA_VERSION

TOOL_NAME = "KiBridge: Inspect Board"

# --- Heuristics. Tune these later. -------------------------------------------
POWER_NET_PATTERNS = [
    r"^\+?12V", r"^\+?5V", r"^\+?3V3", r"^\+?3\.3V",
    r"^VCC", r"^VDD", r"^VBAT", r"^VBUS", r"^VIN", r"^VAA",
]
GND_NET_PATTERNS = [r"^GND", r"^AGND", r"^DGND", r"^PGND", r"^EARTH", r"^0V$"]

MIN_POWER_TRACK_WIDTH_MM = 0.30
SUSPICIOUS_VIA_DRILL_MM = 0.20
# -----------------------------------------------------------------------------


def _nm_to_mm(nm):
    return round(nm / 1_000_000.0, 4)


def _matches_any(name, patterns):
    return any(re.match(p, name, re.IGNORECASE) for p in patterns)


def _classify_net(name):
    if _matches_any(name, GND_NET_PATTERNS):
        return "ground"
    if _matches_any(name, POWER_NET_PATTERNS):
        return "power"
    return "signal"


def _is_via(item):
    try:
        return item.Type() == pcbnew.PCB_VIA_T
    except Exception:
        try:
            return isinstance(item, pcbnew.PCB_VIA)
        except Exception:
            return False


def inspect_board(board):
    """Build a JSON-serialisable report dict. Never modifies the board."""
    fname = board.GetFileName() or ""

    footprints = list(board.GetFootprints())
    all_track_items = list(board.GetTracks())  # tracks AND vias
    zones = list(board.Zones())
    drawings = list(board.GetDrawings())

    tracks = [t for t in all_track_items if not _is_via(t)]
    vias = [t for t in all_track_items if _is_via(t)]

    # --- Build per-net dictionary by walking pads + tracks -------------------
    nets = {}  # netcode -> dict

    def _ensure(code, name):
        if code in nets:
            return nets[code]
        n = {
            "code": code,
            "name": name,
            "class": _classify_net(name),
            "pad_count": 0,
            "track_count": 0,
            "via_count": 0,
            "total_length_mm": 0.0,
            "min_width_mm": None,
        }
        nets[code] = n
        return n

    for fp in footprints:
        for pad in fp.Pads():
            code = pad.GetNetCode()
            if code <= 0:
                continue
            net = pad.GetNet()
            n = _ensure(code, net.GetNetname() if net else f"net{code}")
            n["pad_count"] += 1

    track_widths_mm = set()
    for t in tracks:
        code = t.GetNetCode()
        try:
            w = _nm_to_mm(t.GetWidth())
        except Exception:
            w = None
        if w is not None:
            track_widths_mm.add(w)
        if code <= 0:
            continue
        net = t.GetNet()
        n = _ensure(code, net.GetNetname() if net else f"net{code}")
        n["track_count"] += 1
        try:
            n["total_length_mm"] += _nm_to_mm(t.GetLength())
        except Exception:
            pass
        if w is not None and (n["min_width_mm"] is None or w < n["min_width_mm"]):
            n["min_width_mm"] = w

    via_sizes_mm = set()
    for v in vias:
        code = v.GetNetCode()
        try:
            w = _nm_to_mm(v.GetWidth())
            d = _nm_to_mm(v.GetDrill())
        except Exception:
            continue
        via_sizes_mm.add((w, d))
        if code <= 0:
            continue
        net = v.GetNet()
        n = _ensure(code, net.GetNetname() if net else f"net{code}")
        n["via_count"] += 1

    for n in nets.values():
        n["total_length_mm"] = round(n["total_length_mm"], 3)

    # --- Edge.Cuts presence --------------------------------------------------
    try:
        edge_layer = pcbnew.Edge_Cuts
        has_outline = any(d.GetLayer() == edge_layer for d in drawings)
    except Exception:
        has_outline = False

    # --- Zone fill state -----------------------------------------------------
    unfilled_zones = 0
    for z in zones:
        try:
            if z.GetFilledArea() == 0:
                unfilled_zones += 1
        except Exception:
            pass

    # --- Warnings ------------------------------------------------------------
    warnings = []

    # 1) Nets with pads but no tracks (likely unrouted)
    for n in nets.values():
        if n["pad_count"] >= 2 and n["track_count"] == 0:
            warnings.append({
                "level": "error" if n["class"] != "signal" else "warning",
                "code":  "NET_NOT_ROUTED",
                "net":   n["name"],
                "message": (
                    f"Net '{n['name']}' has {n['pad_count']} pads but no tracks "
                    "(likely unrouted)."
                ),
            })

    # 2) Power/GND tracks below the heuristic minimum width
    for n in nets.values():
        if n["class"] in ("power", "ground") and n["min_width_mm"] is not None:
            if n["min_width_mm"] < MIN_POWER_TRACK_WIDTH_MM:
                warnings.append({
                    "level": "warning",
                    "code":  "POWER_TRACK_TOO_THIN",
                    "net":   n["name"],
                    "message": (
                        f"Power/GND net '{n['name']}' has track narrower than "
                        f"{MIN_POWER_TRACK_WIDTH_MM} mm "
                        f"(min observed {n['min_width_mm']} mm)."
                    ),
                })

    # 3) Suspiciously small via drills
    for w, d in via_sizes_mm:
        if d < SUSPICIOUS_VIA_DRILL_MM:
            warnings.append({
                "level": "warning",
                "code":  "VIA_DRILL_SMALL",
                "message": (
                    f"Via with {d} mm drill is below typical PCB-house minimum "
                    f"({SUSPICIOUS_VIA_DRILL_MM} mm). Confirm with manufacturer."
                ),
            })

    # 4) No board outline
    if not has_outline:
        warnings.append({
            "level": "error",
            "code":  "MISSING_OUTLINE",
            "message": "No drawings on Edge.Cuts layer - board outline missing.",
        })

    # 5) Unfilled zones
    if unfilled_zones > 0:
        warnings.append({
            "level": "warning",
            "code":  "ZONES_NOT_FILLED",
            "message": (
                f"{unfilled_zones} zone(s) appear unfilled. Run "
                "'Edit > Fill All Zones' (B) before generating Gerbers."
            ),
        })

    # --- Assemble final report ----------------------------------------------
    nets_list = sorted(nets.values(), key=lambda n: n["name"])
    power_nets = [n for n in nets_list if n["class"] in ("power", "ground")]

    try:
        kicad_ver = pcbnew.GetBuildVersion()
    except Exception:
        kicad_ver = "unknown"

    return {
        "schema_version": SCHEMA_VERSION,
        "tool":           TOOL_NAME,
        "tool_version":   TOOL_VERSION,
        "kicad_version":  kicad_ver,
        "board": {
            "filename": os.path.basename(fname) if fname else "",
            "path":     fname,
        },
        "counts": {
            "footprints": len(footprints),
            "tracks":     len(tracks),
            "vias":       len(vias),
            "zones":      len(zones),
            "drawings":   len(drawings),
            "nets":       len(nets_list),
        },
        "track_widths_mm": sorted(track_widths_mm),
        "via_sizes_mm":    [
            {"width_mm": w, "drill_mm": d} for w, d in sorted(via_sizes_mm)
        ],
        "has_board_outline": has_outline,
        "unfilled_zones":    unfilled_zones,
        "nets":        nets_list,
        "power_nets":  power_nets,
        "warnings":    warnings,
    }
