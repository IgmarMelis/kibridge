"""
kirouter_client - the plugin side of the KiBridge <-> KiRouter bridge.

Two responsibilities:
  1. Build a board JSON in KiRouter's schema from a KiCad Board object.
     Reuses the same primitives as the workspace exporter so plugin and
     workspace dumps stay in lock-step.
  2. Talk HTTP to localhost:8765 using only the stdlib (urllib) - no
     extra deps shipped to KiCad.

We deliberately do NOT depend on Flask or anything KiRouter-specific.
The plugin must keep working even if KiRouter isn't installed; the only
contract is the JSON shape and the HTTP endpoints.
"""
from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime
from typing import Any
from urllib import request as urlrequest
from urllib import error as urlerror

import pcbnew  # type: ignore

from . import workspace_exporter as wx_exp
from .version import TOOL_VERSION, SCHEMA_VERSION


# Same defaults the server uses. Plugin never accepts a non-localhost
# host - this is a local-only system.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT_SECONDS = 10


# ---- URL plumbing ----------------------------------------------------------
def base_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    if host not in ("127.0.0.1", "localhost", "::1"):
        # Hard refusal mirrors the server-side guard
        raise ValueError(
            f"refusing to talk to non-local host {host!r}; "
            "KiRouter is local-only."
        )
    return f"http://{host}:{port}"


def is_server_up(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 timeout: float = 1.5) -> tuple[bool, str]:
    """
    Lightweight probe: hits /api/health. Returns (ok, detail).
    'detail' is the version string on success, or an error message.
    """
    try:
        url = base_url(host, port) + "/api/health"
        with urlrequest.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return False, f"server returned HTTP {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
            return True, f"{data.get('product','?')} v{data.get('version','?')}"
    except (urlerror.URLError, socket.timeout) as e:
        return False, _connection_hint(e)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _connection_hint(e: Exception) -> str:
    msg = str(e)
    if "Connection refused" in msg or "actively refused" in msg:
        return ("server unreachable - is KiRouter running?\n"
                "Start it: double-click router/START_KIROUTER.bat")
    if "timed out" in msg.lower():
        return "server didn't respond in time"
    return f"network error: {msg}"


# ---- Board -> KiRouter JSON ------------------------------------------------
def build_board_json(board) -> dict:
    """
    Produce the JSON KiRouter expects (POST /api/board).

    NOTE: we do NOT reuse workspace_exporter._export_footprints here -
    that one only writes pad_count (an integer). KiRouter needs the full
    pad list with net names. So we walk footprints + pads + nets directly.
    """
    footprints = _export_footprints_with_pads(board)
    tracks_and_vias = wx_exp._export_tracks(board)
    design_rules = wx_exp._export_design_rules(board)

    try:
        kicad_ver = pcbnew.GetBuildVersion()
    except Exception:
        kicad_ver = "unknown"

    bbox = _board_bbox(board)

    return {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "plugin_version": TOOL_VERSION,
            "kicad_version":  kicad_ver,
            "board_path":     board.GetFileName() or "",
            "exported_at":    datetime.now().isoformat(timespec="seconds"),
            "board_bbox":     bbox,
        },
        "design_rules": design_rules,
        "footprints":   footprints,
        "tracks":       tracks_and_vias.get("tracks", []),
        "vias":         tracks_and_vias.get("vias", []),
    }


def _export_footprints_with_pads(board) -> list[dict]:
    """
    Walk every footprint and every pad. Returns the list format
    KiRouter's schema expects, with pads carrying their net names.
    """
    out: list[dict] = []
    for fp in board.GetFootprints():
        try:
            ref = fp.GetReference() or "?"
        except Exception:
            ref = "?"
        try:
            val = fp.GetValue() or ""
        except Exception:
            val = ""
        try:
            layer = wx_exp._layer_name(board, fp.GetLayer())
        except Exception:
            layer = "F.Cu"
        try:
            rot_deg = float(fp.GetOrientationDegrees())
        except Exception:
            rot_deg = 0.0
        try:
            pos = fp.GetPosition()
            fx_mm = wx_exp._nm_to_mm(pos.x)
            fy_mm = wx_exp._nm_to_mm(pos.y)
        except Exception:
            fx_mm, fy_mm = 0.0, 0.0

        pads_out: list[dict] = []
        try:
            pads_iter = list(fp.Pads())
        except Exception:
            pads_iter = []

        for pad in pads_iter:
            try:
                pad_num = pad.GetPadName() or pad.GetNumber() or ""
            except Exception:
                try:
                    pad_num = pad.GetNumber() or ""
                except Exception:
                    pad_num = ""

            # Pad absolute position (the centre of the pad in board coords)
            try:
                pp = pad.GetPosition()
                px_mm = wx_exp._nm_to_mm(pp.x)
                py_mm = wx_exp._nm_to_mm(pp.y)
            except Exception:
                continue  # skip a pad with no position

            try:
                sz = pad.GetSize()
                sx_mm = wx_exp._nm_to_mm(sz.x)
                sy_mm = wx_exp._nm_to_mm(sz.y)
            except Exception:
                sx_mm, sy_mm = 1.0, 1.0

            try:
                shape_int = pad.GetShape()
                shape_str = _pad_shape_name(shape_int)
            except Exception:
                shape_str = "rect"

            try:
                net_name = pad.GetNetname() or ""
            except Exception:
                net_name = ""

            pads_out.append({
                "number":   str(pad_num),
                "x_mm":     round(px_mm, 4),
                "y_mm":     round(py_mm, 4),
                "size_mm":  [round(sx_mm, 4), round(sy_mm, 4)],
                "shape":    shape_str,
                "net":      net_name,
            })

        out.append({
            "ref":           ref,
            "value":         val,
            "layer":         layer,
            "rotation_deg":  round(rot_deg, 2),
            "x_mm":          round(fx_mm, 4),
            "y_mm":          round(fy_mm, 4),
            "pads":          pads_out,
        })
    return sorted(out, key=lambda f: f["ref"])


def _pad_shape_name(shape_int) -> str:
    """
    Map pcbnew's PAD_SHAPE enum to our string form. We can't import
    pcbnew constants at module load time without a board context, so
    we look them up dynamically by name.
    """
    try:
        if shape_int == pcbnew.PAD_SHAPE_CIRCLE:
            return "circle"
        if shape_int == pcbnew.PAD_SHAPE_OVAL:
            return "oval"
        if shape_int == pcbnew.PAD_SHAPE_TRAPEZOID:
            return "trapezoid"
        if shape_int == pcbnew.PAD_SHAPE_ROUNDRECT:
            return "rect"     # treat rounded rect as rect for routing
        if shape_int == pcbnew.PAD_SHAPE_RECT:
            return "rect"
    except AttributeError:
        pass
    return "rect"


def _board_bbox(board) -> dict:
    """
    Compute a bounding box that ALWAYS contains every footprint and pad,
    plus the drawn board outline if present. Adds a generous margin.

    Why both? The Edge.Cuts outline alone is unreliable - many in-progress
    boards have Edge.Cuts smaller than the components (or missing entirely).
    The footprint bbox alone is also unreliable - it misses pads that
    extend beyond the footprint origin. So we union them and pad.
    """
    xs: list[float] = []
    ys: list[float] = []

    # Edge.Cuts contribution (if any)
    try:
        bb = board.GetBoardEdgesBoundingBox()
        if bb and bb.GetWidth() > 0 and bb.GetHeight() > 0:
            xs.append(wx_exp._nm_to_mm(bb.GetX()))
            ys.append(wx_exp._nm_to_mm(bb.GetY()))
            xs.append(wx_exp._nm_to_mm(bb.GetX() + bb.GetWidth()))
            ys.append(wx_exp._nm_to_mm(bb.GetY() + bb.GetHeight()))
    except Exception:
        pass

    # Footprint + pad contribution (the critical part)
    for fp in board.GetFootprints():
        try:
            pos = fp.GetPosition()
            xs.append(wx_exp._nm_to_mm(pos.x))
            ys.append(wx_exp._nm_to_mm(pos.y))
        except Exception:
            pass
        # Pad positions are what really matters: footprint origin can be
        # off-centre, and pads extend in all directions from there.
        try:
            for pad in fp.Pads():
                try:
                    pp = pad.GetPosition()
                    xs.append(wx_exp._nm_to_mm(pp.x))
                    ys.append(wx_exp._nm_to_mm(pp.y))
                except Exception:
                    continue
        except Exception:
            continue

    if not xs:
        return {"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100}

    # 10mm margin around the union, so routing has working room
    MARGIN = 10.0
    return {
        "x_min": round(min(xs) - MARGIN, 3),
        "y_min": round(min(ys) - MARGIN, 3),
        "x_max": round(max(xs) + MARGIN, 3),
        "y_max": round(max(ys) + MARGIN, 3),
    }


# ---- HTTP send / receive ---------------------------------------------------
def post_board(board_json: dict, *, host: str = DEFAULT_HOST,
               port: int = DEFAULT_PORT,
               timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """POST /api/board?source=kibridge. Returns server response dict."""
    url = base_url(host, port) + "/api/board?source=kibridge"
    body = json.dumps(board_json).encode("utf-8")
    req = urlrequest.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_result(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
               timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict | None:
    """
    GET /api/result. Returns the routed-board payload, or None if no
    completed result is available (HTTP 404).
    """
    url = base_url(host, port) + "/api/result"
    try:
        with urlrequest.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as e:
        if e.code == 404:
            return None
        raise


def get_info(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
             timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """GET /api/info — for showing the user what's currently loaded."""
    url = base_url(host, port) + "/api/info"
    with urlrequest.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---- Apply tracks/vias back to KiCad ---------------------------------------
def apply_routes_to_board(board, added_tracks: list[dict],
                          added_vias:   list[dict]) -> dict:
    """
    Add tracks and vias to a KiCad Board object. Returns a summary dict:
      { 'tracks_added': N, 'vias_added': M, 'errors': [...] }

    The board is NOT saved here; the caller calls pcbnew.SaveBoard()
    after backing up the original file.
    """
    errors: list[str] = []
    tracks_added = 0
    vias_added   = 0

    # Cache nets by name once
    netinfo = board.GetNetInfo()
    name_to_net: dict[str, Any] = {}
    for i in range(netinfo.GetNetCount()):
        net = netinfo.GetNetItem(i)
        name = net.GetNetname()
        if name:
            name_to_net[name] = net

    # Layer name -> layer id
    layer_name_to_id = {
        "F.Cu": pcbnew.F_Cu,
        "B.Cu": pcbnew.B_Cu,
    }

    for t in added_tracks:
        try:
            net_name = t.get("net", "")
            net = name_to_net.get(net_name)
            if net is None:
                errors.append(f"track skipped — unknown net '{net_name}'")
                continue
            layer = layer_name_to_id.get(t.get("layer", "F.Cu"))
            if layer is None:
                errors.append(f"track skipped — unknown layer '{t.get('layer')}'")
                continue
            start = t.get("start") or {}
            end   = t.get("end")   or {}
            sx = _mm_to_nm(start.get("x_mm", 0))
            sy = _mm_to_nm(start.get("y_mm", 0))
            ex = _mm_to_nm(end.get("x_mm",   0))
            ey = _mm_to_nm(end.get("y_mm",   0))
            width = _mm_to_nm(t.get("width_mm", 0.25))

            seg = pcbnew.PCB_TRACK(board)
            seg.SetStart(pcbnew.VECTOR2I(sx, sy))
            seg.SetEnd(pcbnew.VECTOR2I(ex, ey))
            seg.SetWidth(width)
            seg.SetLayer(layer)
            seg.SetNet(net)
            board.Add(seg)
            tracks_added += 1
        except Exception as e:
            errors.append(f"track add failed: {type(e).__name__}: {e}")

    for v in added_vias:
        try:
            net_name = v.get("net", "")
            net = name_to_net.get(net_name)
            if net is None:
                errors.append(f"via skipped — unknown net '{net_name}'")
                continue
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I(
                _mm_to_nm(v.get("x_mm", 0)),
                _mm_to_nm(v.get("y_mm", 0)),
            ))
            via.SetWidth(_mm_to_nm(v.get("width_mm", 0.6)))
            via.SetDrill(_mm_to_nm(v.get("drill_mm", 0.3)))
            via.SetNet(net)
            # Through-hole via spans all copper layers
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            board.Add(via)
            vias_added += 1
        except Exception as e:
            errors.append(f"via add failed: {type(e).__name__}: {e}")

    return {
        "tracks_added": tracks_added,
        "vias_added":   vias_added,
        "errors":       errors,
    }


def backup_board_file(board_path: str) -> str:
    """
    Make a timestamped backup of the .kicad_pcb file. Returns backup path.
    Uses kibridge_backup_ prefix per project naming convention.
    """
    if not board_path or not os.path.isfile(board_path):
        raise FileNotFoundError(f"board file not found: {board_path}")
    directory = os.path.dirname(board_path)
    basename  = os.path.basename(board_path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"kibridge_backup_{stamp}_{basename}"
    backup_path = os.path.join(directory, backup_name)
    # Use raw bytes to dodge encoding issues
    with open(board_path, "rb") as src, open(backup_path, "wb") as dst:
        dst.write(src.read())
    return backup_path


def _mm_to_nm(mm: float) -> int:
    return int(round(float(mm) * 1_000_000))
