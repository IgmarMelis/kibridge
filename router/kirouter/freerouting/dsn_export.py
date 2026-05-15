"""
DSN exporter — converts a KiRouter board JSON into a Specctra DSN file
that Freerouting can read.

DSN reference: Specctra Design File Format (Cadence/Allegro), version 4.x.
We emit a minimal but complete subset: structure (layers + boundary +
classes), placement, library (image + padstacks), network (nets), wiring
(existing tracks + vias).

Units: DSN works in user units we declare. We use micrometres (um) so
integer math stays clean (1 mm = 1000 um).

This is a textual format. We hand-build the s-expressions; no library
needed.
"""
from __future__ import annotations

import io
from typing import Any


# DSN works best when all coords are integer micrometres.
def _um(mm: float) -> int:
    """True micrometres — used in human-readable padstack names."""
    return int(round(mm * 1000))


# We declare (resolution um 10) below, which means each integer coord in
# the DSN file body represents 0.1 um. So mm * 10000 = file integer.
# Using a separate helper keeps padstack names (e.g. "Pad_1500_um") in
# human-readable um while body coords get the correct file-unit scaling.
def _dsn(mm: float) -> int:
    return int(round(mm * 10000))


# Pre-defined padstack name per (shape, w_um, h_um). Reused across pads.
# IMPORTANT: padstack names cannot contain '[' or ']' — Freerouting's
# parser splits tokens on those characters and fails with
# "number expected" errors. Stick to alphanumerics + underscore.
def _padstack_name(shape: str, w_um: int, h_um: int) -> str:
    if shape == "circle":
        return f"Round_Pad_{w_um}_um"
    return f"Rect_Pad_{w_um}x{h_um}_um"


def export_dsn(board: dict, board_name: str = "kirouter_board") -> str:
    """
    Produce a Specctra DSN string for the given board JSON.
    Caller writes it to disk and passes the path to Freerouting.
    """
    bbox = _bbox(board)
    layers = _layers_present(board)
    if "F.Cu" not in layers:
        layers.append("F.Cu")
    if "B.Cu" not in layers:
        layers.append("B.Cu")
    layers = [l for l in layers if l in ("F.Cu", "B.Cu")]

    nets = _collect_nets(board)
    padstacks = _collect_padstacks(board)
    components = _collect_components(board, padstacks)

    out = io.StringIO()
    w = out.write

    w(f"(pcb {board_name}\n")
    w("  (parser\n")
    w("    (string_quote \")\n")
    w("    (space_in_quoted_tokens on)\n")
    w("    (host_cad \"KiRouter\")\n")
    w('    (host_version "1.0.0")\n')
    w("  )\n")
    w("  (resolution um 10)\n")
    w("  (unit um)\n")

    # ---- structure ---------------------------------------------------------
    w("  (structure\n")
    for layer in layers:
        side = "front" if layer == "F.Cu" else "back"
        w(f"    (layer {layer}\n")
        w(f"      (type signal)\n")
        w(f"      (property (index {0 if layer=='F.Cu' else 1}))\n")
        w(f"    )\n")

    # Boundary as a rectangle, one per layer + a global one.
    x1, y1 = _dsn(bbox["x_min"]), _dsn(bbox["y_min"])
    x2, y2 = _dsn(bbox["x_max"]), _dsn(bbox["y_max"])
    w('    (boundary\n')
    w(f'      (rect pcb {x1} {y1} {x2} {y2})\n')
    w('    )\n')

    # Default via padstack
    w("    (via \"Via_600_300\")\n")

    # Default rule: track width 250um, clearance 200um
    rules = (board.get("design_rules") or {}).get("design_settings") or {}
    default_track_um = max(_dsn(rules.get("min_track_width_mm", 0.25)), 1000)
    default_clear_um = max(_dsn(rules.get("min_clearance_mm",  0.2)),  1000)
    w(f"    (rule\n")
    w(f"      (width {default_track_um})\n")
    w(f"      (clearance {default_clear_um})\n")
    w(f"      (clearance {default_clear_um} (type smd_smd))\n")
    w(f"    )\n")
    w("  )\n")

    # ---- placement ---------------------------------------------------------
    w("  (placement\n")
    for comp_image, items in components.items():
        w(f"    (component {comp_image}\n")
        for it in items:
            side = "front" if it["layer"] == "F.Cu" else "back"
            w(f"      (place {it['ref']} {it['x_dsn']} {it['y_dsn']} "
              f"{side} {int(it['rot'])} (PN {it['value']}))\n")
        w("    )\n")
    w("  )\n")

    # ---- library: padstacks + component images ----------------------------
    w("  (library\n")
    for image_name, fp_pads in components.items():
        # Pull pads from the first instance — all instances of an image share pads
        sample = fp_pads[0]
        w(f"    (image {image_name}\n")
        for pad in sample["pads"]:
            num   = str(pad.get("number", "")).strip()
            # Skip pads with no number — these are NPTH (non-plated
            # through-hole) / mechanical pads that don't participate in
            # routing. Emitting "(pin <ps>  <x> <y>)" with a blank number
            # causes Freerouting to fail with "number expected".
            if not num:
                continue
            ps = pad["padstack"]
            x_dsn = _dsn(pad["dx_mm"])
            y_dsn = _dsn(pad["dy_mm"])
            w(f"      (pin {ps} {num} {x_dsn} {y_dsn})\n")
        w("    )\n")
    # Padstacks
    for ps_name, ps_def in padstacks.items():
        w(f"    (padstack {ps_name}\n")
        # Convert recorded um values to file units (×10 for resolution 10)
        w_dsn_val = ps_def["w_um"] * 10
        h_dsn_val = ps_def["h_um"] * 10
        for layer in ("F.Cu", "B.Cu"):
            if ps_def["shape"] == "circle":
                w(f"      (shape (circle {layer} {w_dsn_val}))\n")
            else:
                hw = w_dsn_val // 2
                hh = h_dsn_val // 2
                w(f"      (shape (rect {layer} -{hw} -{hh} {hw} {hh}))\n")
        w("      (attach off)\n")
        w("    )\n")
    # Default via padstack (600um diameter -> 6000 in file units)
    w("    (padstack Via_600_300\n")
    w("      (shape (circle F.Cu 6000))\n")
    w("      (shape (circle B.Cu 6000))\n")
    w("      (attach off)\n")
    w("    )\n")
    w("  )\n")

    # ---- network -----------------------------------------------------------
    w("  (network\n")
    for net_name, pin_list in nets.items():
        if net_name == "":
            continue
        w(f'    (net "{_escape(net_name)}"\n')
        w('      (pins')
        for pin in pin_list:
            w(f' {pin}')
        w(')\n')
        w("    )\n")
    # net class
    w("    (class kicad_default\n")
    for net_name in nets:
        if net_name == "":
            continue
        w(f'      "{_escape(net_name)}"\n')
    w("      (circuit\n")
    w("        (use_via Via_600_300)\n")
    w("      )\n")
    w(f"      (rule (width {default_track_um}) (clearance {default_clear_um}))\n")
    w("    )\n")
    w("  )\n")

    # ---- wiring (pre-routed copper that should be kept) -------------------
    pre_tracks = board.get("tracks") or []
    pre_vias   = board.get("vias")   or []
    if pre_tracks or pre_vias:
        w("  (wiring\n")
        for t in pre_tracks:
            net = t.get("net", "")
            layer = t.get("layer", "F.Cu")
            if layer not in ("F.Cu", "B.Cu"):
                continue
            width_dsn = max(_dsn(t.get("width_mm", 0.25)), 1000)
            sx, sy = _dsn(t["start"]["x_mm"]), _dsn(t["start"]["y_mm"])
            ex, ey = _dsn(t["end"]["x_mm"]),   _dsn(t["end"]["y_mm"])
            w(f"    (wire (path {layer} {width_dsn} {sx} {sy} {ex} {ey}) "
              f'(net "{_escape(net)}") (type protect))\n')
        for v in pre_vias:
            net = v.get("net", "")
            x_dsn, y_dsn = _dsn(v["x_mm"]), _dsn(v["y_mm"])
            w(f'    (via Via_600_300 {x_dsn} {y_dsn} (net "{_escape(net)}") (type protect))\n')
        w("  )\n")

    w(")\n")
    return out.getvalue()


# ---- helpers ---------------------------------------------------------------
def _bbox(board: dict) -> dict:
    meta = board.get("meta") or {}
    if meta.get("board_bbox"):
        return meta["board_bbox"]
    # Fallback: derive from footprints
    xs, ys = [], []
    for fp in board.get("footprints", []):
        xs.append(fp.get("x_mm", 0))
        ys.append(fp.get("y_mm", 0))
        for pad in fp.get("pads", []):
            xs.append(pad["x_mm"])
            ys.append(pad["y_mm"])
    if not xs:
        return {"x_min": 0, "y_min": 0, "x_max": 50, "y_max": 50}
    pad = 5
    return {
        "x_min": min(xs) - pad, "y_min": min(ys) - pad,
        "x_max": max(xs) + pad, "y_max": max(ys) + pad,
    }


def _layers_present(board: dict) -> list[str]:
    seen: list[str] = []
    for t in board.get("tracks", []):
        L = t.get("layer")
        if L and L not in seen:
            seen.append(L)
    for fp in board.get("footprints", []):
        L = fp.get("layer")
        if L and L not in seen:
            seen.append(L)
    return seen


def _collect_nets(board: dict) -> dict[str, list[str]]:
    """Map net name -> list of '<refdes>-<padnumber>' pin identifiers."""
    out: dict[str, list[str]] = {}
    for fp in board.get("footprints", []):
        ref = fp.get("ref", "")
        if not ref:
            continue
        for pad in fp.get("pads", []):
            net = pad.get("net", "")
            if not net:
                continue
            num = str(pad.get("number", "")).strip()
            if not num:
                # NPTH / mechanical pads: skipped in image, must be
                # skipped here too or Freerouting will see a net pinning
                # a pad that doesn't exist in the component image.
                continue
            out.setdefault(net, []).append(f"{ref}-{num}")
    return out


def _collect_padstacks(board: dict) -> dict[str, dict[str, Any]]:
    """Build unique padstack definitions keyed by name."""
    out: dict[str, dict[str, Any]] = {}
    for fp in board.get("footprints", []):
        for pad in fp.get("pads", []):
            shape = pad.get("shape", "rect")
            sx = (pad.get("size_mm") or [1, 1])[0]
            sy = (pad.get("size_mm") or [1, 1])[1]
            w_um, h_um = _um(sx), _um(sy)
            name = _padstack_name(shape, w_um, h_um)
            if name not in out:
                out[name] = {"shape": shape, "w_um": w_um, "h_um": h_um}
    return out


def _collect_components(board: dict, padstacks: dict) -> dict[str, list[dict]]:
    """
    Group footprints by a synthetic 'image' name. We use refdes-as-image so
    every footprint becomes its own image in the library — simpler than
    deduplicating across identical footprints, and Freerouting accepts it.
    """
    out: dict[str, list[dict]] = {}
    for fp in board.get("footprints", []):
        ref = fp.get("ref")
        if not ref:
            continue
        image_name = f"img_{ref}"
        cx, cy = fp.get("x_mm", 0), fp.get("y_mm", 0)
        pads_rel = []
        for pad in fp.get("pads", []):
            shape = pad.get("shape", "rect")
            sx = (pad.get("size_mm") or [1, 1])[0]
            sy = (pad.get("size_mm") or [1, 1])[1]
            ps = _padstack_name(shape, _um(sx), _um(sy))
            pads_rel.append({
                "padstack": ps,
                "number":   str(pad.get("number", "1")),
                "dx_mm":    pad["x_mm"] - cx,
                "dy_mm":    pad["y_mm"] - cy,
            })
        out.setdefault(image_name, []).append({
            "ref":   ref,
            "value": fp.get("value", "?"),
            "x_dsn": _dsn(cx),
            "y_dsn": _dsn(cy),
            "rot":   fp.get("rotation_deg", 0),
            "layer": fp.get("layer", "F.Cu"),
            "pads":  pads_rel,
        })
    return out


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')
