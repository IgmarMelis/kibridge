"""
Example KiBridge script - run by the plugin via the sandboxed runner.

This is what Copilot might generate when asked to widen all power nets.
The ONLY allowed import is kibridge_api. The runner will refuse the script
if it sees anything else.
"""
import kibridge_api

# Power-like net name patterns to look for in the live board.
POWER_PATTERNS = ("5V", "3.3V", "3V3", "12V", "VCC", "VDD", "VBAT")
TARGET_WIDTH_MM = 0.6

# Fetch the actual nets present on the board.
nets = kibridge_api.list_nets()

for net in nets:
    upper = net.upper()
    if any(p in upper for p in POWER_PATTERNS):
        n = kibridge_api.set_track_widths_for_net(net, TARGET_WIDTH_MM)
        print(f"[widen] {net}: set {n} track(s) to {TARGET_WIDTH_MM}mm")

# Annotate the board with a note recording what was done.
kibridge_api.add_silkscreen_note(
    text=f"KB: power nets widened to {TARGET_WIDTH_MM}mm",
    x_mm=10.0,
    y_mm=10.0,
    layer="F.SilkS",
    size_mm=1.0,
)
