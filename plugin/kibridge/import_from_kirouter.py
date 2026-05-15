"""
KiBridge: Import from KiRouter

Action plugin button. Pulls the routed board result from KiRouter via
GET /api/result, shows the user a confirmation dialog with what's about
to change, backs up the .kicad_pcb, then adds the new tracks and vias
to the board. The user must save the .kicad_pcb themselves (Ctrl+S) -
KiCad's own save dialog is the right confirmation here.

Refuses to import if the board path doesn't match what was sent, or if
the server has no result yet.
"""
import os
import traceback

import wx
import pcbnew  # type: ignore

from .version import TOOL_VERSION
from .kirouter_client import (
    get_result, get_info, is_server_up,
    apply_routes_to_board, backup_board_file,
    DEFAULT_HOST, DEFAULT_PORT,
)


PLUGIN_NAME = "KiBridge: Import from KiRouter"


class KiBridgeImportFromKiRouter(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = PLUGIN_NAME
        self.category = "PSS Tools"
        self.description = (
            f"{PLUGIN_NAME} v{TOOL_VERSION} - pull the routed board from "
            "the KiRouter web app and apply it to the open PCB."
        )
        self.show_toolbar_button = True
        icon = os.path.join(os.path.dirname(__file__), "icon_import.png")
        if os.path.exists(icon):
            self.icon_file_name = icon

    def Run(self):
        try:
            board = pcbnew.GetBoard()
            if board is None:
                wx.MessageBox(
                    "No board is open in the PCB Editor.",
                    self.name, wx.OK | wx.ICON_WARNING,
                )
                return

            board_path = board.GetFileName() or ""
            if not board_path or not os.path.isfile(board_path):
                wx.MessageBox(
                    "This board has never been saved. Save it once "
                    "(File > Save) before importing routes - "
                    "the backup needs a file to copy.",
                    self.name, wx.OK | wx.ICON_WARNING,
                )
                return

            # Probe server
            up, detail = is_server_up()
            if not up:
                wx.MessageBox(
                    f"Can't reach KiRouter at {DEFAULT_HOST}:{DEFAULT_PORT}\n\n"
                    f"{detail}",
                    self.name, wx.OK | wx.ICON_ERROR,
                )
                return

            # Fetch info first to check whether the server has the same
            # board loaded that we sent.
            info = get_info()
            if not info.get("loaded"):
                wx.MessageBox(
                    f"KiRouter has no board loaded.\n\n"
                    f"Did you forget to click 'Send to KiRouter' first?",
                    self.name, wx.OK | wx.ICON_WARNING,
                )
                return

            # Best-effort path match - warn but don't block
            sent_path = (info.get("meta") or {}).get("board_path", "")
            path_mismatch = (
                sent_path
                and os.path.normpath(sent_path) != os.path.normpath(board_path)
            )

            # Pull the result
            result = get_result()
            if result is None:
                wx.MessageBox(
                    f"KiRouter has a board loaded but no routing result yet.\n\n"
                    f"Open KiRouter in your browser:\n"
                    f"  http://{DEFAULT_HOST}:{DEFAULT_PORT}/\n\n"
                    f"Click 'Auto-route' and wait for it to finish, then\n"
                    f"come back here.",
                    self.name, wx.OK | wx.ICON_WARNING,
                )
                return

            added_tracks = result.get("added_tracks") or []
            added_vias   = result.get("added_vias")   or []
            engine       = result.get("engine", "?")
            elapsed      = result.get("elapsed", 0)

            if not added_tracks and not added_vias:
                wx.MessageBox(
                    "The route result contains no new tracks or vias.\n"
                    "Nothing to import.",
                    self.name, wx.OK | wx.ICON_INFORMATION,
                )
                return

            # Confirmation dialog - tell the user exactly what's about to happen
            warning = ""
            if path_mismatch:
                warning = (
                    "\n\nWARNING: the path KiRouter has loaded\n"
                    f"  ({sent_path})\n"
                    "does not match the open board\n"
                    f"  ({board_path}).\n"
                    "The routes may not match this PCB."
                )

            confirm = wx.MessageBox(
                f"About to import from KiRouter:\n\n"
                f"  Engine    : {engine}\n"
                f"  Routed in : {elapsed:.1f}s\n"
                f"  New tracks: {len(added_tracks)}\n"
                f"  New vias  : {len(added_vias)}\n\n"
                f"This will:\n"
                f"  1. Back up {os.path.basename(board_path)}\n"
                f"  2. Add the tracks and vias to the open board\n"
                f"  3. Mark the PCB as modified (save with Ctrl+S)\n"
                f"{warning}\n\n"
                f"Proceed?",
                self.name, wx.YES_NO | wx.ICON_QUESTION,
            )
            if confirm != wx.YES:
                return

            # Backup
            try:
                backup_path = backup_board_file(board_path)
            except Exception as e:
                wx.MessageBox(
                    f"Backup failed - aborting.\n\n{e}",
                    self.name, wx.OK | wx.ICON_ERROR,
                )
                return

            # Apply
            apply_summary = apply_routes_to_board(
                board, added_tracks, added_vias)

            # Refresh the PCB editor's view
            try:
                pcbnew.Refresh()
            except Exception:
                pass

            errors = apply_summary.get("errors", [])
            err_block = ""
            if errors:
                err_block = (
                    f"\n\nSome items failed ({len(errors)}):\n"
                    + "\n".join(f"  - {e}" for e in errors[:8])
                    + ("\n  ..." if len(errors) > 8 else "")
                )

            wx.MessageBox(
                f"{PLUGIN_NAME} v{TOOL_VERSION} - import complete.\n\n"
                f"Added:\n"
                f"  Tracks: {apply_summary['tracks_added']} / {len(added_tracks)}\n"
                f"  Vias  : {apply_summary['vias_added']} / {len(added_vias)}\n\n"
                f"Backup: {backup_path}\n\n"
                f"Press Ctrl+S to save your changes.\n"
                f"If something looks wrong, close without saving and"
                f" restore from the backup file."
                f"{err_block}",
                self.name, wx.OK | wx.ICON_INFORMATION,
            )

        except Exception as e:
            wx.MessageBox(
                f"{PLUGIN_NAME} crashed.\n\n{e}\n\n{traceback.format_exc()}",
                self.name, wx.OK | wx.ICON_ERROR,
            )
