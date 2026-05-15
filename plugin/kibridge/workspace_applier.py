"""
workspace_applier - read kibridge_workspace/review/, validate, preview, apply.

Inputs read:
  review/actions.json          (declarative ops)
  review/scripts/*.py          (Python scripts, AST-validated)

Process:
  1. Load and validate actions.json against the strict schema.
  2. Validate every script with the AST checker (no execution yet).
  3. Run a DRY-RUN pass to collect what would be done.
  4. (Plugin shows a preview dialog around this and asks for confirmation.)
  5. Backup the .kicad_pcb to backups/.
  6. Run actions and scripts for real.
  7. Save board.
  8. Write apply_log/<timestamp>_apply.log
"""
from __future__ import annotations

import os
import json
import glob
from datetime import datetime

import pcbnew  # type: ignore

from . import kibridge_api
from .script_runner import run_script, validate_script, ScriptValidationError
from .safety import backup_board
from .version import TOOL_VERSION


REVIEW_SUBDIR = "review"
SCRIPTS_SUBDIR = os.path.join("review", "scripts")
APPLY_LOG_SUBDIR = "apply_log"
BACKUPS_SUBDIR = "backups"

# Whitelist of action ops mapped to kibridge_api functions
ACTION_OPS = {
    "add_silkscreen_note":      kibridge_api.add_silkscreen_note,
    "add_fab_note":             kibridge_api.add_fab_note,
    "add_user_marker":          kibridge_api.add_user_marker,
    "highlight_net":            kibridge_api.highlight_net,
    "set_track_widths_for_net": kibridge_api.set_track_widths_for_net,
    "add_stitching_via":        kibridge_api.add_stitching_via,
}

MODIFYING_OPS = {
    "set_track_widths_for_net",
    "add_stitching_via",
}


class ReviewValidationError(Exception):
    """Raised when actions.json or a script fails validation."""


# --- Loading & validation ----------------------------------------------------
def load_review(workspace_root: str) -> dict:
    """Load actions.json + list scripts. Raises ReviewValidationError on issues."""
    review_dir = os.path.join(workspace_root, REVIEW_SUBDIR)
    actions_path = os.path.join(review_dir, "actions.json")

    actions_data = {"schema_version": 1, "actions": []}
    if os.path.isfile(actions_path):
        try:
            with open(actions_path, "r", encoding="utf-8") as f:
                actions_data = json.load(f)
        except Exception as e:
            raise ReviewValidationError(
                f"actions.json is not valid JSON: {e}") from e

    actions = actions_data.get("actions", [])
    if not isinstance(actions, list):
        raise ReviewValidationError("actions.json: 'actions' must be a list")

    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            raise ReviewValidationError(
                f"actions[{i}] is not an object")
        op = a.get("op")
        if op not in ACTION_OPS:
            raise ReviewValidationError(
                f"actions[{i}].op = '{op}' is not whitelisted. "
                f"Allowed: {sorted(ACTION_OPS)}"
            )

    # Modifying ops require explicit confirm_changes flag at the top level
    has_mod = any(a.get("op") in MODIFYING_OPS for a in actions)
    if has_mod and not actions_data.get("confirm_changes", False):
        raise ReviewValidationError(
            "actions.json contains modifying ops but 'confirm_changes' is "
            "not set to true at the top level."
        )

    # Scripts
    scripts_dir = os.path.join(workspace_root, SCRIPTS_SUBDIR)
    script_files = []
    if os.path.isdir(scripts_dir):
        script_files = sorted(glob.glob(os.path.join(scripts_dir, "*.py")))

    scripts = []
    for sp in script_files:
        try:
            with open(sp, "r", encoding="utf-8") as f:
                src = f.read()
        except Exception as e:
            raise ReviewValidationError(
                f"could not read script {sp}: {e}") from e
        try:
            validate_script(src, filename=os.path.basename(sp))
        except ScriptValidationError as e:
            raise ReviewValidationError(str(e)) from e
        scripts.append({"path": sp, "source": src})

    return {
        "actions_data": actions_data,
        "actions": actions,
        "scripts": scripts,
        "has_modifying_ops": has_mod,
    }


# --- Dry run ----------------------------------------------------------------
def dry_run(board, review: dict) -> list[dict]:
    """Run all actions+scripts in dry-run mode. Returns combined log."""
    combined_log: list[dict] = []

    kibridge_api._board = board
    kibridge_api._dry_run = True
    kibridge_api._log = []

    for a in review["actions"]:
        _exec_action(a, dry_run=True)
        combined_log.extend(kibridge_api._log)
        kibridge_api._log = []

    kibridge_api._board = None

    for s in review["scripts"]:
        log = run_script(s["source"], kibridge_api, board, dry_run=True,
                         filename=os.path.basename(s["path"]))
        for entry in log:
            entry["_from_script"] = os.path.basename(s["path"])
        combined_log.extend(log)
    return combined_log


# --- Apply (real) ------------------------------------------------------------
def apply_real(board, workspace_root: str, review: dict) -> dict:
    """
    Backup the board, run actions+scripts for real, save, write log.
    Returns a summary dict.
    """
    board_path = board.GetFileName() or ""
    backups_dir = os.path.join(workspace_root, BACKUPS_SUBDIR)
    backup_path = backup_board(board_path, backups_dir)

    combined_log: list[dict] = []
    errors: list[dict] = []

    kibridge_api._board = board
    kibridge_api._dry_run = False
    kibridge_api._log = []

    for i, a in enumerate(review["actions"]):
        try:
            _exec_action(a, dry_run=False)
        except Exception as e:
            errors.append({"action_index": i, "op": a.get("op"), "error": str(e)})
        combined_log.extend(kibridge_api._log)
        kibridge_api._log = []

    kibridge_api._board = None

    for s in review["scripts"]:
        try:
            log = run_script(s["source"], kibridge_api, board, dry_run=False,
                             filename=os.path.basename(s["path"]))
        except Exception as e:
            errors.append({"script": os.path.basename(s["path"]), "error": str(e)})
            log = []
        for entry in log:
            entry["_from_script"] = os.path.basename(s["path"])
        combined_log.extend(log)

    # Save board if anything changed
    try:
        pcbnew.SaveBoard(board_path, board)
    except Exception as e:
        errors.append({"phase": "save", "error": str(e)})

    # Refresh editor view
    try:
        pcbnew.Refresh()
    except Exception:
        pass

    # Write log
    log_path = _write_log(workspace_root, board_path, backup_path,
                          review, combined_log, errors)

    return {
        "backup_path": backup_path,
        "log_path": log_path,
        "applied": len(combined_log),
        "errors": errors,
    }


def _exec_action(action: dict, dry_run: bool):
    op = action["op"]
    fn = ACTION_OPS[op]
    # Build kwargs from the action dict, excluding 'op' itself.
    kwargs = {k: v for k, v in action.items() if k != "op"}
    fn(**kwargs)


def _write_log(workspace_root, board_path, backup_path, review,
               combined_log, errors):
    log_dir = os.path.join(workspace_root, APPLY_LOG_SUBDIR)
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"{ts}_apply.json")
    payload = {
        "plugin_version": TOOL_VERSION,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "board_path": board_path,
        "backup_path": backup_path,
        "actions_summary": [
            {"op": a.get("op")} for a in review["actions"]
        ],
        "scripts_run": [os.path.basename(s["path"]) for s in review["scripts"]],
        "operation_log": combined_log,
        "errors": errors,
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return log_path
