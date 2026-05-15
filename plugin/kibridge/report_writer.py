"""
KiBridge Inspector - report writers.

Writes the inspection dict to JSON and TXT files in
<board_dir>/kibridge_reports/. Never touches the .kicad_pcb file.
"""
import os
import json
from datetime import datetime


def _output_dir(board_path):
    if not board_path:
        return os.path.expanduser("~")
    out = os.path.join(os.path.dirname(board_path), "kibridge_reports")
    os.makedirs(out, exist_ok=True)
    return out


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_reports(board, report):
    """Write JSON + TXT reports. Returns (json_path, txt_path)."""
    board_path = board.GetFileName() or ""
    base = os.path.splitext(os.path.basename(board_path))[0] or "board"
    out_dir = _output_dir(board_path)
    ts = _timestamp()

    json_path = os.path.join(out_dir, f"{base}_kibridge_inspect_{ts}.json")
    txt_path = os.path.join(out_dir, f"{base}_kibridge_inspect_{ts}.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(_format_txt(report))

    return json_path, txt_path


def _format_txt(r):
    out = []
    bar = "=" * 68
    out += [bar, f"  {r['tool']}  v{r['tool_version']}", bar]
    out.append(f"KiCad        : {r['kicad_version']}")
    out.append(f"Board file   : {r['board']['filename']}")
    out.append(f"Board path   : {r['board']['path']}")
    out.append("")
    out.append("-- Counts --")
    for k, v in r["counts"].items():
        out.append(f"  {k:11s}: {v}")
    out.append("")
    out.append(f"Board outline (Edge.Cuts) present : {r['has_board_outline']}")
    out.append(f"Unfilled zones                    : {r['unfilled_zones']}")
    out.append("")
    out.append(
        "Track widths used (mm): "
        + (", ".join(str(w) for w in r["track_widths_mm"]) or "-")
    )
    out.append("Via sizes used (width / drill, mm):")
    if r["via_sizes_mm"]:
        for v in r["via_sizes_mm"]:
            out.append(f"  - {v['width_mm']} / {v['drill_mm']}")
    else:
        out.append("  (none)")
    out.append("")
    out.append("-- Power & ground nets --")
    if r["power_nets"]:
        for n in r["power_nets"]:
            out.append(
                f"  {n['name']:14s} [{n['class']:6s}]  "
                f"pads={n['pad_count']:3d}  tracks={n['track_count']:4d}  "
                f"vias={n['via_count']:3d}  len={n['total_length_mm']} mm  "
                f"min_w={n['min_width_mm']}"
            )
    else:
        out.append("  (none detected by name)")
    out.append("")
    out.append(f"-- Warnings ({len(r['warnings'])}) --")
    if not r["warnings"]:
        out.append("  No warnings.")
    else:
        for w in r["warnings"]:
            net = f" [{w['net']}]" if "net" in w else ""
            out.append(
                f"  [{w['level'].upper():7s}] {w['code']}{net}: {w['message']}"
            )
    out += ["", bar, "End of report"]
    return "\n".join(out)
