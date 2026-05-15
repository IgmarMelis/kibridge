"""
'KiBridge: Apply Workspace' action plugin.

Reads kibridge_workspace/review/, validates everything, runs a dry-run, shows
a preview dialog with checkboxes, then (only if confirmed) backs up the
.kicad_pcb and applies for real.
"""
import os
import traceback

import wx
import pcbnew  # type: ignore

from .workspace_exporter import workspace_root_for
from .workspace_applier import (
    load_review, dry_run, apply_real, ReviewValidationError,
    MODIFYING_OPS,
)
from .version import TOOL_VERSION

PLUGIN_NAME = "KiBridge: Apply Workspace"


class KiBridgeApplyWorkspace(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = PLUGIN_NAME
        self.category = "PSS Tools"
        self.description = (
            f"KiBridge v{TOOL_VERSION} - validate the review folder "
            "(actions + scripts), preview, backup, then apply."
        )
        self.show_toolbar_button = True
        icon = os.path.join(os.path.dirname(__file__), "icon_apply.png")
        if os.path.exists(icon):
            self.icon_file_name = icon

    def Run(self):
        try:
            board = pcbnew.GetBoard()
            if board is None:
                wx.MessageBox(
                    "No board is currently open.",
                    self.name, wx.OK | wx.ICON_WARNING,
                )
                return

            ws_root = workspace_root_for(board)
            if not os.path.isdir(ws_root):
                wx.MessageBox(
                    f"No kibridge_workspace/ folder found next to the board.\n\n"
                    f"Expected: {ws_root}\n\n"
                    "Run 'KiBridge: Open Workspace' first.",
                    self.name, wx.OK | wx.ICON_WARNING,
                )
                return

            try:
                review = load_review(ws_root)
            except ReviewValidationError as e:
                wx.MessageBox(
                    f"Review validation failed:\n\n{e}\n\n"
                    "No changes were applied.",
                    self.name, wx.OK | wx.ICON_ERROR,
                )
                return

            if not review["actions"] and not review["scripts"]:
                wx.MessageBox(
                    "Nothing to apply.\n\n"
                    "review/actions.json has no actions and "
                    "review/scripts/ contains no .py files.",
                    self.name, wx.OK | wx.ICON_INFORMATION,
                )
                return

            # Dry run to preview
            try:
                preview_log = dry_run(board, review)
            except Exception as e:
                wx.MessageBox(
                    f"Dry-run failed:\n\n{e}\n\n"
                    f"{traceback.format_exc()}\n\n"
                    "No changes were applied.",
                    self.name, wx.OK | wx.ICON_ERROR,
                )
                return

            confirmed = _confirm_dialog(review, preview_log)
            if not confirmed:
                return

            result = apply_real(board, ws_root, review)

            err_lines = ""
            if result["errors"]:
                err_lines = "\n\nErrors:\n" + "\n".join(
                    f"  - {e}" for e in result["errors"]
                )

            wx.MessageBox(
                f"Apply complete.\n\n"
                f"Operations applied: {result['applied']}\n"
                f"Backup           : {result['backup_path']}\n"
                f"Log              : {result['log_path']}"
                f"{err_lines}",
                self.name,
                wx.OK | wx.ICON_INFORMATION if not result["errors"]
                else wx.OK | wx.ICON_WARNING,
            )

        except Exception as e:
            wx.MessageBox(
                f"{PLUGIN_NAME} crashed.\n\n{e}\n\n{traceback.format_exc()}",
                self.name, wx.OK | wx.ICON_ERROR,
            )


def _confirm_dialog(review: dict, preview_log: list) -> bool:
    """
    Show a preview dialog summarising what will be done. The user must
    explicitly click 'Apply' for it to proceed. Modifying ops require
    a separate second confirmation.
    """
    n_actions = len(review["actions"])
    n_scripts = len(review["scripts"])
    has_mod = review["has_modifying_ops"] or any(
        e.get("op") in MODIFYING_OPS or
        (e.get("op", "").startswith(tuple(MODIFYING_OPS)))
        for e in preview_log
    )

    lines = [f"Preview - {len(preview_log)} operation(s) would be performed."]
    lines.append("")
    lines.append(f"Actions  : {n_actions}")
    lines.append(f"Scripts  : {n_scripts}")
    lines.append("")
    lines.append("Operations:")
    for entry in preview_log[:40]:
        op = entry.get("op", "?")
        bits = []
        for k in ("net", "text", "x_mm", "y_mm", "width_mm", "count", "layer"):
            if k in entry:
                bits.append(f"{k}={entry[k]}")
        src = entry.get("_from_script", "actions.json")
        lines.append(f"  - [{src}] {op}  " + " ".join(bits))
    if len(preview_log) > 40:
        lines.append(f"  ... and {len(preview_log) - 40} more")
    lines.append("")
    if has_mod:
        lines.append("WARNING: this includes MODIFYING ops on existing geometry.")
        lines.append("A backup will be made first.")
    lines.append("")
    lines.append("Apply now?")

    text = "\n".join(lines)
    answer = wx.MessageBox(text, PLUGIN_NAME, wx.YES_NO | wx.ICON_QUESTION)
    if answer != wx.YES:
        return False

    if has_mod:
        answer2 = wx.MessageBox(
            "Final confirmation:\n\nThis will modify your board. "
            "A timestamped backup will be saved to "
            "kibridge_workspace/backups/.\n\nProceed?",
            PLUGIN_NAME, wx.YES_NO | wx.ICON_WARNING,
        )
        if answer2 != wx.YES:
            return False
    return True
