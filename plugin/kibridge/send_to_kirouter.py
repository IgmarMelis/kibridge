"""
KiBridge: Send to KiRouter

Action plugin button. Builds the current board's JSON snapshot and POSTs
it to http://localhost:8765/api/board. Shows a wx.MessageBox confirming
what was sent, or a clear error if KiRouter isn't running.
"""
import os
import traceback

import wx
import pcbnew  # type: ignore

from .version import TOOL_VERSION
from .kirouter_client import (
    build_board_json, post_board, is_server_up,
    DEFAULT_HOST, DEFAULT_PORT,
)


PLUGIN_NAME = "KiBridge: Send to KiRouter"


class KiBridgeSendToKiRouter(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = PLUGIN_NAME
        self.category = "PSS Tools"
        self.description = (
            f"{PLUGIN_NAME} v{TOOL_VERSION} - push the current board to "
            "the KiRouter web app for autorouting."
        )
        self.show_toolbar_button = True
        icon = os.path.join(os.path.dirname(__file__), "icon_send.png")
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

            # Probe server first - clear error beats a 30-second hang
            up, detail = is_server_up()
            if not up:
                wx.MessageBox(
                    f"Can't reach KiRouter at {DEFAULT_HOST}:{DEFAULT_PORT}\n\n"
                    f"{detail}\n\n"
                    f"To start KiRouter:\n"
                    f"  1. Open the 'router' folder in the KiBridge repo\n"
                    f"  2. Double-click START_KIROUTER.bat (Windows)\n"
                    f"     or run ./start_kirouter.sh (macOS/Linux)\n"
                    f"  3. Wait for your browser to open KiRouter\n"
                    f"  4. Click this button again",
                    self.name, wx.OK | wx.ICON_ERROR,
                )
                return

            # Build and post
            board_json = build_board_json(board)

            counts = {
                "footprints": len(board_json.get("footprints", [])),
                "tracks":     len(board_json.get("tracks", [])),
                "vias":       len(board_json.get("vias", [])),
            }

            response = post_board(board_json)
            if not response.get("ok"):
                wx.MessageBox(
                    f"KiRouter rejected the board:\n\n"
                    f"{response.get('error', 'no detail')}",
                    self.name, wx.OK | wx.ICON_ERROR,
                )
                return

            info = response.get("info", {}) or {}
            srv_counts = info.get("counts", {}) or {}

            summary = (
                f"{PLUGIN_NAME} v{TOOL_VERSION}\n\n"
                f"Connected to: {detail}\n\n"
                f"Sent:\n"
                f"  Footprints : {counts['footprints']}\n"
                f"  Tracks     : {counts['tracks']}\n"
                f"  Vias       : {counts['vias']}\n"
                f"  Nets       : {srv_counts.get('nets', '?')}\n\n"
                f"Now open KiRouter in your browser:\n"
                f"  http://{DEFAULT_HOST}:{DEFAULT_PORT}/\n\n"
                f"Then click 'Auto-route' to route the board.\n"
                f"When done, come back here and click\n"
                f"'KiBridge: Import from KiRouter'."
            )
            wx.MessageBox(summary, self.name, wx.OK | wx.ICON_INFORMATION)

        except Exception as e:
            wx.MessageBox(
                f"{PLUGIN_NAME} crashed.\n\n{e}\n\n{traceback.format_exc()}",
                self.name, wx.OK | wx.ICON_ERROR,
            )
