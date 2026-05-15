"""
SES parser — reads a Freerouting session output (.ses) and extracts the
routed wires + vias as additions to a board JSON.

A .ses file is a Specctra session file. It contains the routed result —
wires laid down by the router and any vias inserted. We parse the
s-expression form with a small hand-rolled tokenizer and walk the tree,
emitting our standard track/via dicts.

Coordinates in the SES come back in the same unit we declared in the DSN
(micrometres). We convert back to millimetres in the output.
"""
from __future__ import annotations

from typing import Any


# ---- s-expression tokenizer / parser ---------------------------------------
def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == "(" or c == ")":
            out.append(c)
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1]); j += 2; continue
                if text[j] == '"':
                    break
                buf.append(text[j])
                j += 1
            out.append('"' + "".join(buf) + '"')
            i = j + 1
            continue
        # bare token
        j = i
        while j < n and not text[j].isspace() and text[j] not in "()":
            j += 1
        out.append(text[i:j])
        i = j
    return out


def _parse(tokens: list[str], idx: int) -> tuple[list, int]:
    if tokens[idx] != "(":
        raise ValueError(f"expected '(' at {idx}, got {tokens[idx]!r}")
    idx += 1
    out: list[Any] = []
    while idx < len(tokens):
        t = tokens[idx]
        if t == ")":
            return out, idx + 1
        if t == "(":
            sub, idx = _parse(tokens, idx)
            out.append(sub)
            continue
        if t.startswith('"') and t.endswith('"'):
            out.append(t[1:-1])
        else:
            out.append(t)
        idx += 1
    raise ValueError("unexpected EOF — unclosed list")


def parse_sexpr(text: str) -> list:
    tokens = _tokenize(text)
    if not tokens:
        return []
    if tokens[0] != "(":
        # Some SES files start with a top-level (session ...). Wrap if needed.
        raise ValueError("SES does not start with '('")
    tree, _ = _parse(tokens, 0)
    return tree


# ---- semantic walk ---------------------------------------------------------
def parse_ses(text: str, reference_board: dict | None = None) -> dict[str, list]:
    """
    Walk the parsed s-expression tree and pull out wires + vias.
    Returns:
      { "tracks": [...], "vias": [...] }
    in the same shape as our board JSON.

    The SES file declares `(resolution um N)` like the DSN does, BUT
    Freerouting v2.x has a known bug where it writes coordinates with
    10× more precision than its own resolution declaration says. So a
    SES with `(resolution um 10)` actually has coords in 0.01 µm units,
    not 0.1 µm as declared.

    When `reference_board` is supplied (the original board JSON sent to
    Freerouting), we cross-check the placement section of the SES
    against the known footprint positions to auto-detect the true
    scale. This is robust against Freerouting fixing the bug in a
    future release.
    """
    tree = parse_sexpr(text)
    if not tree or tree[0] != "session":
        return {"tracks": [], "vias": []}

    # Resolution and unit live under the "routes" subtree.
    unit, scale = _find_unit_scale(tree)

    # Auto-detect scale by comparing SES placements with the reference
    # board's footprint positions. Falls back to declared scale on
    # failure or when no reference is given.
    if reference_board is not None:
        detected = _detect_scale_from_placement(tree, reference_board)
        if detected is not None:
            scale = detected

    tracks: list[dict] = []
    vias:   list[dict] = []

    routes = _find_subtree(tree, "routes")
    if routes is None:
        return {"tracks": tracks, "vias": vias}

    network_out = _find_subtree(routes, "network_out")
    if network_out is None:
        return {"tracks": tracks, "vias": vias}

    for child in network_out[1:]:
        if not isinstance(child, list) or not child:
            continue
        if child[0] == "net":
            net_name = child[1] if len(child) > 1 else ""
            if isinstance(net_name, str):
                net_name = net_name.strip('"')
            for sub in child[2:]:
                if not isinstance(sub, list) or not sub:
                    continue
                if sub[0] == "wire":
                    track = _parse_wire(sub, net_name, scale)
                    if track is not None:
                        tracks.extend(track)
                elif sub[0] == "via":
                    via = _parse_via(sub, net_name, scale)
                    if via is not None:
                        vias.append(via)
    return {"tracks": tracks, "vias": vias}


def _find_subtree(tree: list, head: str) -> list | None:
    if not isinstance(tree, list):
        return None
    for item in tree:
        if isinstance(item, list) and item and item[0] == head:
            return item
    return None


def _detect_scale_from_placement(tree: list,
                                  reference_board: dict) -> float | None:
    """
    Compare the SES placement section against the reference board's
    footprint positions to figure out what coordinate scale Freerouting
    is actually using. Returns mm_per_unit, or None if detection fails.

    SES placement looks like:
        (placement
          (resolution um 10)
          (component "img_A1" (place A1 2055500 2208500 front 0))
          ...)

    Reference board footprint A1 has x_mm=20.555. So if SES says
    2055500 == 20.555 mm, then mm_per_unit = 20.555 / 2055500 ≈ 1e-5.
    """
    placement = _find_subtree(tree, "placement")
    if placement is None:
        return None

    # Build refdes -> (x_mm, y_mm) from the reference board
    ref_pos: dict[str, tuple[float, float]] = {}
    for fp in reference_board.get("footprints", []):
        ref = fp.get("ref")
        if ref:
            try:
                ref_pos[ref] = (float(fp["x_mm"]), float(fp["y_mm"]))
            except Exception:
                continue

    if not ref_pos:
        return None

    ratios: list[float] = []
    for item in placement[1:]:
        if not isinstance(item, list) or not item:
            continue
        if item[0] != "component":
            continue
        # (component "name" (place REFDES x y side rot))
        for sub in item[2:]:
            if not isinstance(sub, list) or len(sub) < 4 or sub[0] != "place":
                continue
            refdes = sub[1]
            try:
                ses_x = float(sub[2])
                ses_y = float(sub[3])
            except Exception:
                continue
            if refdes not in ref_pos:
                continue
            ref_x, ref_y = ref_pos[refdes]
            if abs(ses_x) > 1 and abs(ref_x) > 0.001:
                ratios.append(ref_x / ses_x)
            if abs(ses_y) > 1 and abs(ref_y) > 0.001:
                ratios.append(ref_y / ses_y)

    if not ratios:
        return None

    # Use the median to be robust against outliers (e.g. a component
    # at origin would give a 0/0). All real ratios should match closely.
    ratios.sort()
    median = ratios[len(ratios) // 2]
    return median


def _find_unit_scale(tree: list) -> tuple[str, float]:
    """Return (unit, mm_per_unit). Default um, 0.001 mm per um."""
    routes = _find_subtree(tree, "routes")
    target = routes if routes is not None else tree
    res = _find_subtree(target, "resolution")
    if res and len(res) >= 3:
        unit = res[1]
        try:
            divisor = float(res[2])
        except Exception:
            divisor = 10.0
        # res[2] is "10" meaning 10 units per ... actually Freerouting's
        # convention: (resolution um 10) means 10 sub-units per um.
        # But coordinates are still in um. So mm_per_unit = 0.001 / divisor.
        if unit == "um":
            return unit, 0.001 / divisor if divisor else 0.001
        if unit == "mm":
            return unit, 1.0 / divisor if divisor else 1.0
        if unit == "inch":
            return unit, 25.4 / divisor if divisor else 25.4
        if unit == "mil":
            return unit, 0.0254 / divisor if divisor else 0.0254
    return "um", 0.0001  # safe default


def _parse_wire(node: list, net: str, scale: float) -> list[dict] | None:
    # (wire (path <layer> <width> x1 y1 x2 y2 ... xn yn) (type ...))
    path = _find_subtree(node, "path")
    if not path or len(path) < 6:
        return None
    layer = path[1]
    try:
        width_units = float(path[2])
    except Exception:
        return None
    coords = path[3:]
    nums: list[float] = []
    for c in coords:
        try:
            nums.append(float(c))
        except Exception:
            break
    if len(nums) < 4 or len(nums) % 2 != 0:
        return None
    width_mm = round(width_units * scale, 4)
    out = []
    for i in range(0, len(nums) - 2, 2):
        x1, y1 = nums[i] * scale, nums[i + 1] * scale
        x2, y2 = nums[i + 2] * scale, nums[i + 3] * scale
        out.append({
            "net":      net,
            "layer":    layer,
            "width_mm": width_mm,
            "length_mm": round(((x2-x1)**2 + (y2-y1)**2)**0.5, 3),
            "start": {"x_mm": round(x1, 4), "y_mm": round(y1, 4)},
            "end":   {"x_mm": round(x2, 4), "y_mm": round(y2, 4)},
        })
    return out


def _parse_via(node: list, net: str, scale: float) -> dict | None:
    # (via <padstack> x y)
    if len(node) < 4:
        return None
    try:
        x = float(node[2]) * scale
        y = float(node[3]) * scale
    except Exception:
        return None
    return {
        "net":      net,
        "layer":    "F.Cu/B.Cu",
        "x_mm":     round(x, 4),
        "y_mm":     round(y, 4),
        "width_mm": 0.6,
        "drill_mm": 0.3,
    }
