"""
kibridge_api - the SAFE API for KiBridge workspace scripts.

This is the ONLY module that scripts in kibridge_workspace/review/scripts/
are allowed to import. The script_runner enforces this with AST checks.

Every function:
  - takes coordinates in millimetres (not pcbnew internal units),
  - never raises on invalid input (logs a warning, returns False),
  - respects a global dry_run flag - when True, no board mutation happens.

Coordinate system: same as KiCad (origin top-left, +X right, +Y down).

Layer names accepted as strings: "F.SilkS", "B.SilkS", "F.Fab",
"B.Fab", "User.1".

The active BOARD and dry_run flag are injected by the runner before
execution. Do not import this module from your script as a normal
import target outside the runner; it will not have a board attached.
"""
from __future__ import annotations

import pcbnew  # type: ignore

# These get set by script_runner.run_script() before execution.
_board = None
_dry_run = True
_log: list = []  # list of dicts describing each successful op

# --- Layer name -> pcbnew constant ------------------------------------------
_LAYER_MAP = {
    "F.SilkS": pcbnew.F_SilkS,
    "B.SilkS": pcbnew.B_SilkS,
    "F.Fab":   pcbnew.F_Fab,
    "B.Fab":   pcbnew.B_Fab,
    "User.1":  pcbnew.User_1,
    "F.Cu":    pcbnew.F_Cu,
    "B.Cu":    pcbnew.B_Cu,
}


# --- Helpers (not part of the public API) -----------------------------------
def _mm_to_nm(mm: float) -> int:
    return int(round(mm * 1_000_000))


def _vec(x_mm: float, y_mm: float):
    """Build a VECTOR2I from mm. KiCad 7+ uses VECTOR2I; falls back to wxPoint."""
    nm = (_mm_to_nm(x_mm), _mm_to_nm(y_mm))
    if hasattr(pcbnew, "VECTOR2I"):
        return pcbnew.VECTOR2I(*nm)
    return pcbnew.wxPoint(*nm)


def _layer(name: str) -> int:
    if name not in _LAYER_MAP:
        raise ValueError(f"Unknown layer '{name}'. Allowed: {sorted(_LAYER_MAP)}")
    return _LAYER_MAP[name]


def _record(op: str, **kw):
    _log.append({"op": op, **kw})


# --- Read-only helpers (always safe) ----------------------------------------
def list_nets() -> list[str]:
    """Return all net names on the board."""
    if _board is None:
        return []
    out = []
    for fp in _board.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNet()
            if n is not None:
                name = n.GetNetname()
                if name and name not in out:
                    out.append(name)
    return sorted(out)


def find_net_code(net_name: str) -> int | None:
    """Resolve a net name to its netcode, or None if not found."""
    if _board is None:
        return None
    for fp in _board.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNet()
            if n is not None and n.GetNetname() == net_name:
                return n.GetNetCode()
    return None


# --- Additive ops (always safe - never destructive) -------------------------
def add_silkscreen_note(text: str, x_mm: float, y_mm: float,
                        layer: str = "F.SilkS", size_mm: float = 1.0) -> bool:
    """
    Add a text note on a silkscreen layer. Purely additive.
    layer: "F.SilkS" or "B.SilkS"
    """
    if layer not in ("F.SilkS", "B.SilkS"):
        raise ValueError("silkscreen layer must be 'F.SilkS' or 'B.SilkS'")
    return _add_text(text, x_mm, y_mm, layer, size_mm, op="add_silkscreen_note")


def add_fab_note(text: str, x_mm: float, y_mm: float,
                 layer: str = "F.Fab", size_mm: float = 1.0) -> bool:
    """Add a text note on a fab layer."""
    if layer not in ("F.Fab", "B.Fab"):
        raise ValueError("fab layer must be 'F.Fab' or 'B.Fab'")
    return _add_text(text, x_mm, y_mm, layer, size_mm, op="add_fab_note")


def add_user_marker(x_mm: float, y_mm: float, radius_mm: float = 1.5,
                    note: str = "") -> bool:
    """
    Add a circle on User.1 at (x,y) with optional text label below it.
    User.1 is a designer-visible layer that is NOT exported to Gerbers
    by default - safe for review markers.
    """
    if _board is None:
        return False
    if _dry_run:
        _record("add_user_marker", x_mm=x_mm, y_mm=y_mm,
                radius_mm=radius_mm, note=note, dry_run=True)
        return True
    try:
        circle = pcbnew.PCB_SHAPE(_board)
        circle.SetShape(pcbnew.SHAPE_T_CIRCLE)
        circle.SetLayer(_layer("User.1"))
        circle.SetCenter(_vec(x_mm, y_mm))
        circle.SetEnd(_vec(x_mm + radius_mm, y_mm))
        try:
            circle.SetWidth(_mm_to_nm(0.15))
        except Exception:
            pass
        _board.Add(circle)
        if note:
            _add_text(note, x_mm, y_mm + radius_mm + 1.0,
                      "User.1", 0.8, op="add_user_marker_label", silent=True)
        _record("add_user_marker", x_mm=x_mm, y_mm=y_mm,
                radius_mm=radius_mm, note=note, dry_run=False)
        return True
    except Exception as e:
        _record("add_user_marker_FAILED", error=str(e),
                x_mm=x_mm, y_mm=y_mm)
        return False


def highlight_net(net_name: str) -> bool:
    """
    Visually highlight all items on a net. Pure selection, zero modification.
    """
    if _board is None:
        return False
    code = find_net_code(net_name)
    if code is None:
        _record("highlight_net_FAILED", reason="net not found", net=net_name)
        return False
    if _dry_run:
        _record("highlight_net", net=net_name, dry_run=True)
        return True
    try:
        for t in _board.GetTracks():
            if t.GetNetCode() == code:
                t.SetSelected()
        _record("highlight_net", net=net_name, dry_run=False)
        return True
    except Exception as e:
        _record("highlight_net_FAILED", error=str(e), net=net_name)
        return False


# --- Modifying ops (require explicit confirm in actions.json) ---------------
def set_track_widths_for_net(net_name: str, width_mm: float) -> int:
    """
    Set the width of EVERY track on the given net. Vias are not changed.
    Returns the count of tracks modified (or that would be modified in dry-run).
    """
    if _board is None or width_mm <= 0:
        return 0
    code = find_net_code(net_name)
    if code is None:
        _record("set_track_widths_for_net_FAILED",
                reason="net not found", net=net_name)
        return 0
    width_nm = _mm_to_nm(width_mm)
    n = 0
    try:
        for t in _board.GetTracks():
            if t.GetNetCode() != code:
                continue
            try:
                if t.Type() == pcbnew.PCB_VIA_T:
                    continue
            except Exception:
                pass
            if not _dry_run:
                t.SetWidth(width_nm)
            n += 1
        _record("set_track_widths_for_net",
                net=net_name, width_mm=width_mm, count=n, dry_run=_dry_run)
        return n
    except Exception as e:
        _record("set_track_widths_for_net_FAILED",
                error=str(e), net=net_name)
        return 0


def add_stitching_via(x_mm: float, y_mm: float, net_name: str,
                      width_mm: float = 0.6, drill_mm: float = 0.3) -> bool:
    """
    Add a through-hole via at (x,y) connecting F.Cu to B.Cu, on the given net.
    Useful for stitching a ground pour. Net must already exist on the board.
    """
    if _board is None:
        return False
    code = find_net_code(net_name)
    if code is None:
        _record("add_stitching_via_FAILED",
                reason="net not found", net=net_name)
        return False
    if _dry_run:
        _record("add_stitching_via", x_mm=x_mm, y_mm=y_mm,
                net=net_name, width_mm=width_mm, drill_mm=drill_mm,
                dry_run=True)
        return True
    try:
        via = pcbnew.PCB_VIA(_board)
        via.SetPosition(_vec(x_mm, y_mm))
        via.SetWidth(_mm_to_nm(width_mm))
        via.SetDrill(_mm_to_nm(drill_mm))
        via.SetNetCode(code)
        try:
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        except Exception:
            pass
        _board.Add(via)
        _record("add_stitching_via", x_mm=x_mm, y_mm=y_mm,
                net=net_name, width_mm=width_mm, drill_mm=drill_mm,
                dry_run=False)
        return True
    except Exception as e:
        _record("add_stitching_via_FAILED", error=str(e),
                x_mm=x_mm, y_mm=y_mm, net=net_name)
        return False


# --- Internal text helper ---------------------------------------------------
def _add_text(text: str, x_mm: float, y_mm: float,
              layer: str, size_mm: float, op: str,
              silent: bool = False) -> bool:
    if _board is None:
        return False
    if _dry_run:
        if not silent:
            _record(op, text=text, x_mm=x_mm, y_mm=y_mm,
                    layer=layer, size_mm=size_mm, dry_run=True)
        return True
    try:
        t = pcbnew.PCB_TEXT(_board)
        t.SetText(text)
        t.SetLayer(_layer(layer))
        t.SetPosition(_vec(x_mm, y_mm))
        try:
            t.SetTextSize(_vec(size_mm, size_mm))
        except Exception:
            pass
        _board.Add(t)
        if not silent:
            _record(op, text=text, x_mm=x_mm, y_mm=y_mm,
                    layer=layer, size_mm=size_mm, dry_run=False)
        return True
    except Exception as e:
        _record(f"{op}_FAILED", error=str(e),
                text=text, x_mm=x_mm, y_mm=y_mm)
        return False
