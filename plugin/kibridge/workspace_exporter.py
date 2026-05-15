"""
workspace_exporter - dump complete board state into kibridge_workspace/snapshot/.

This is what Copilot reads. It's a much fuller export than the V1 inspector:
  - board_inspect.json   (V1 report)
  - footprints.json      (every footprint with ref, value, position, layer)
  - tracks.json          (every track + via with start/end, width, net)
  - design_rules.json    (net classes, clearances, min widths)
  - meta.json            (workspace metadata, timestamps)

It also creates the workspace folder skeleton on first run, and copies
the .github/copilot-instructions.md template into it.
"""
from __future__ import annotations

import os
import json
import shutil
from datetime import datetime

import pcbnew  # type: ignore

from .board_inspector import inspect_board
from .version import TOOL_VERSION, SCHEMA_VERSION


WORKSPACE_NAME = "kibridge_workspace"
SNAPSHOT_SUBDIR = "snapshot"
REVIEW_SUBDIR = "review"
SCRIPTS_SUBDIR = os.path.join("review", "scripts")
APPLY_LOG_SUBDIR = "apply_log"
BACKUPS_SUBDIR = "backups"
GITHUB_SUBDIR = ".github"


def workspace_root_for(board) -> str:
    """Return the absolute path of kibridge_workspace next to the board file."""
    bp = board.GetFileName() or ""
    base = os.path.dirname(bp) if bp else os.path.expanduser("~")
    return os.path.join(base, WORKSPACE_NAME)


def ensure_workspace(board, plugin_dir: str) -> str:
    """
    Create the workspace folder skeleton if missing, and copy template files
    (.github/copilot-instructions.md, README.md) on first creation.
    Returns the workspace root path.
    """
    root = workspace_root_for(board)
    os.makedirs(root, exist_ok=True)
    for sub in (SNAPSHOT_SUBDIR, REVIEW_SUBDIR, SCRIPTS_SUBDIR,
                APPLY_LOG_SUBDIR, BACKUPS_SUBDIR, GITHUB_SUBDIR):
        os.makedirs(os.path.join(root, sub), exist_ok=True)

    template_root = os.path.normpath(
        os.path.join(plugin_dir, "..", "..", "workspace_template")
    )
    if not os.path.isdir(template_root):
        # When installed into KiCad, the template is shipped alongside the
        # plugin under plugin_dir/workspace_template/
        alt = os.path.join(plugin_dir, "workspace_template")
        if os.path.isdir(alt):
            template_root = alt

    # Copy templated files only if they don't exist (don't clobber user edits).
    if os.path.isdir(template_root):
        _copy_if_missing(
            os.path.join(template_root, ".github", "copilot-instructions.md"),
            os.path.join(root, GITHUB_SUBDIR, "copilot-instructions.md"),
        )
        _copy_if_missing(
            os.path.join(template_root, "README.md"),
            os.path.join(root, "README.md"),
        )
        _copy_if_missing(
            os.path.join(template_root, "review", "findings.md"),
            os.path.join(root, REVIEW_SUBDIR, "findings.md"),
        )
        _copy_if_missing(
            os.path.join(template_root, "review", "actions.json"),
            os.path.join(root, REVIEW_SUBDIR, "actions.json"),
        )
    return root


def _copy_if_missing(src: str, dst: str) -> None:
    if os.path.isfile(src) and not os.path.isfile(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


# --- Snapshot writers --------------------------------------------------------
def export_snapshot(board, workspace_root: str) -> dict:
    """Write all snapshot/*.json files. Returns a dict of relative paths."""
    snap_dir = os.path.join(workspace_root, SNAPSHOT_SUBDIR)
    os.makedirs(snap_dir, exist_ok=True)

    paths = {}

    # 1. The V1 report (extended)
    board_inspect = inspect_board(board)
    paths["board_inspect"] = _write_json(
        snap_dir, "board_inspect.json", board_inspect)

    # 2. Footprints
    paths["footprints"] = _write_json(
        snap_dir, "footprints.json", _export_footprints(board))

    # 3. Tracks + vias
    paths["tracks"] = _write_json(
        snap_dir, "tracks.json", _export_tracks(board))

    # 4. Design rules / net classes
    paths["design_rules"] = _write_json(
        snap_dir, "design_rules.json", _export_design_rules(board))

    # 5. Meta
    try:
        kicad_ver = pcbnew.GetBuildVersion()
    except Exception:
        kicad_ver = "unknown"
    meta = {
        "schema_version": SCHEMA_VERSION,
        "plugin_version": TOOL_VERSION,
        "kicad_version": kicad_ver,
        "board_path": board.GetFileName() or "",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "files": list(paths.keys()) + ["meta"],
    }
    paths["meta"] = _write_json(snap_dir, "meta.json", meta)
    return paths


def _write_json(directory: str, filename: str, data) -> str:
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def _nm_to_mm(nm) -> float:
    try:
        return round(int(nm) / 1_000_000.0, 4)
    except Exception:
        return 0.0


def _layer_name(board, layer_id: int) -> str:
    try:
        return board.GetLayerName(layer_id)
    except Exception:
        return str(layer_id)


def _pos_xy_mm(item) -> dict:
    try:
        p = item.GetPosition()
        return {"x_mm": _nm_to_mm(p.x), "y_mm": _nm_to_mm(p.y)}
    except Exception:
        return {"x_mm": 0.0, "y_mm": 0.0}


def _export_footprints(board) -> dict:
    out = []
    for fp in board.GetFootprints():
        try:
            ref = fp.GetReference()
        except Exception:
            ref = ""
        try:
            val = fp.GetValue()
        except Exception:
            val = ""
        try:
            layer = _layer_name(board, fp.GetLayer())
        except Exception:
            layer = ""
        try:
            rot_deg = fp.GetOrientationDegrees()
        except Exception:
            rot_deg = 0.0
        pad_count = 0
        try:
            pad_count = len(list(fp.Pads()))
        except Exception:
            pass
        out.append({
            "ref": ref,
            "value": val,
            "layer": layer,
            "rotation_deg": round(float(rot_deg), 2),
            "pad_count": pad_count,
            **_pos_xy_mm(fp),
        })
    return {"count": len(out), "footprints": sorted(out, key=lambda f: f["ref"])}


def _export_tracks(board) -> dict:
    tracks = []
    vias = []
    for item in board.GetTracks():
        is_via = False
        try:
            is_via = item.Type() == pcbnew.PCB_VIA_T
        except Exception:
            pass

        net_name = ""
        try:
            n = item.GetNet()
            if n is not None:
                net_name = n.GetNetname()
        except Exception:
            pass

        if is_via:
            try:
                w = _nm_to_mm(item.GetWidth())
                d = _nm_to_mm(item.GetDrill())
            except Exception:
                w, d = 0.0, 0.0
            vias.append({
                "net": net_name,
                "width_mm": w,
                "drill_mm": d,
                **_pos_xy_mm(item),
            })
        else:
            try:
                start = item.GetStart()
                end = item.GetEnd()
                start_xy = {"x_mm": _nm_to_mm(start.x), "y_mm": _nm_to_mm(start.y)}
                end_xy = {"x_mm": _nm_to_mm(end.x), "y_mm": _nm_to_mm(end.y)}
            except Exception:
                start_xy = {"x_mm": 0.0, "y_mm": 0.0}
                end_xy = {"x_mm": 0.0, "y_mm": 0.0}
            try:
                width_mm = _nm_to_mm(item.GetWidth())
            except Exception:
                width_mm = 0.0
            try:
                length_mm = _nm_to_mm(item.GetLength())
            except Exception:
                length_mm = 0.0
            try:
                layer = _layer_name(board, item.GetLayer())
            except Exception:
                layer = ""
            tracks.append({
                "net": net_name,
                "layer": layer,
                "width_mm": width_mm,
                "length_mm": length_mm,
                "start": start_xy,
                "end": end_xy,
            })
    return {
        "track_count": len(tracks),
        "via_count": len(vias),
        "tracks": tracks,
        "vias": vias,
    }


def _export_design_rules(board) -> dict:
    out = {"net_classes": [], "design_settings": {}}
    try:
        ds = board.GetDesignSettings()
    except Exception:
        return out
    try:
        out["design_settings"] = {
            "min_track_width_mm": _nm_to_mm(getattr(ds, "m_TrackMinWidth", 0)),
            "min_via_diameter_mm": _nm_to_mm(getattr(ds, "m_ViasMinSize", 0)),
            "min_via_drill_mm":    _nm_to_mm(getattr(ds, "m_MinThroughDrill", 0)),
            "min_clearance_mm":    _nm_to_mm(getattr(ds, "m_MinClearance", 0)),
        }
    except Exception:
        pass
    # Net classes - the API for these varies a lot across KiCad versions;
    # try a few patterns and degrade gracefully.
    try:
        ncs = ds.GetNetClasses()
        for nc_name in ncs.NetClasses():
            try:
                nc = ncs.Find(nc_name)
                out["net_classes"].append({
                    "name": nc_name,
                    "track_width_mm": _nm_to_mm(nc.GetTrackWidth()),
                    "via_diameter_mm": _nm_to_mm(nc.GetViaDiameter()),
                    "via_drill_mm": _nm_to_mm(nc.GetViaDrill()),
                    "clearance_mm": _nm_to_mm(nc.GetClearance()),
                })
            except Exception:
                continue
    except Exception:
        pass
    return out
