"""
'KiBridge: Open Workspace' action plugin.

Creates the kibridge_workspace/ folder skeleton next to the .kicad_pcb (if it
doesn't exist) and writes a fresh snapshot/ from the currently-open board.
Then offers to open it in the system file browser.
"""
import os
import sys
import subprocess
import traceback

import wx
import pcbnew  # type: ignore

from .workspace_exporter import ensure_workspace, export_snapshot
from .version import TOOL_VERSION

PLUGIN_NAME = "KiBridge: Open Workspace"


class KiBridgeOpenWorkspace(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = PLUGIN_NAME
        self.category = "PSS Tools"
        self.description = (
            f"KiBridge v{TOOL_VERSION} - create/refresh the "
            "kibridge_workspace/ folder next to the board, export a complete "
            "snapshot, and open it for VS Code/Copilot."
        )
        self.show_toolbar_button = True
        icon = os.path.join(os.path.dirname(__file__), "icon_open.png")
        if os.path.exists(icon):
            self.icon_file_name = icon

    def Run(self):
        try:
            board = pcbnew.GetBoard()
            if board is None:
                wx.MessageBox(
                    "No board is currently open in the PCB Editor.",
                    self.name, wx.OK | wx.ICON_WARNING,
                )
                return

            plugin_dir = os.path.dirname(__file__)
            ws_root = ensure_workspace(board, plugin_dir)
            paths = export_snapshot(board, ws_root)

            msg = (
                f"KiBridge Workspace ready at:\n  {ws_root}\n\n"
                f"Snapshot files written:\n"
                + "\n".join(f"  - {os.path.basename(p)}" for p in paths.values())
                + "\n\nNext steps:\n"
                "  1. Open this folder in VS Code.\n"
                "  2. Use GitHub Copilot agent and ask it to review the snapshot.\n"
                "  3. It will write into kibridge_workspace/review/.\n"
                "  4. Come back here and click 'KiBridge: Apply Workspace'.\n\n"
                "Open the workspace folder now?"
            )
            answer = wx.MessageBox(msg, self.name,
                                   wx.YES_NO | wx.ICON_INFORMATION)
            if answer == wx.YES:
                _open_in_explorer(ws_root)

        except Exception as e:
            wx.MessageBox(
                f"{PLUGIN_NAME} crashed.\n\n{e}\n\n{traceback.format_exc()}",
                self.name, wx.OK | wx.ICON_ERROR,
            )


def _open_in_explorer(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
