"""
KiBridge Inspector — V1 read-only board inspection (still available in V2).

Generates a JSON + TXT report under <board>/kibridge_reports/. Does not touch
the .kicad_pcb file. For the workspace-based AI loop, use the
'KiBridge: Open Workspace' button instead.
"""
import os
import traceback

import wx
import pcbnew  # type: ignore

from .board_inspector import inspect_board
from .report_writer import write_reports
from .version import TOOL_VERSION

PLUGIN_NAME = "KiBridge: Inspect Board"


class KiBridgeInspector(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = PLUGIN_NAME
        self.category = "PSS Tools"
        self.description = (
            f"{PLUGIN_NAME} v{TOOL_VERSION} - read-only PCB inspection. "
            "Generates a board summary report (JSON + TXT). Does not modify the board."
        )
        self.show_toolbar_button = True
        icon = os.path.join(os.path.dirname(__file__), "icon_inspector.png")
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

            report = inspect_board(board)
            json_path, txt_path = write_reports(board, report)

            counts_by_level = {"error": 0, "warning": 0, "info": 0}
            for w in report["warnings"]:
                lvl = w.get("level", "info")
                counts_by_level[lvl] = counts_by_level.get(lvl, 0) + 1

            summary = (
                f"{PLUGIN_NAME} v{TOOL_VERSION} - inspection complete.\n\n"
                f"Footprints : {report['counts']['footprints']}\n"
                f"Tracks     : {report['counts']['tracks']}\n"
                f"Vias       : {report['counts']['vias']}\n"
                f"Zones      : {report['counts']['zones']}\n"
                f"Drawings   : {report['counts']['drawings']}\n"
                f"Nets       : {report['counts']['nets']}\n\n"
                f"Errors     : {counts_by_level.get('error', 0)}\n"
                f"Warnings   : {counts_by_level.get('warning', 0)}\n\n"
                f"Reports written to:\n  {json_path}\n  {txt_path}"
            )
            wx.MessageBox(summary, self.name, wx.OK | wx.ICON_INFORMATION)

        except Exception as e:
            wx.MessageBox(
                f"{PLUGIN_NAME} crashed.\n\n{e}\n\n{traceback.format_exc()}",
                self.name, wx.OK | wx.ICON_ERROR,
            )
