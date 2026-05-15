"""
Unit tests for DSN export and SES import.

These don't run Freerouting — they verify our converters in isolation.
"""
import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "router"))

from kirouter.freerouting import export_dsn, parse_ses, parse_sexpr


def main() -> int:
    failures = []

    def check(label, ok, *, detail=""):
        if ok:
            print(f"  OK   {label}")
        else:
            failures.append(label)
            print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")

    # ---- 1. DSN export of the sample board --------------------------------
    sample_path = os.path.join(REPO_ROOT, "router", "kirouter",
                               "static", "sample_board.json")
    with open(sample_path, encoding="utf-8") as f:
        board = json.load(f)

    dsn = export_dsn(board, "test_board")
    check("DSN starts with (pcb",          dsn.startswith("(pcb"))
    check("DSN ends with )",                dsn.rstrip().endswith(")"))
    check("DSN declares unit um",           "(unit um)" in dsn)
    check("DSN has resolution",             "(resolution um" in dsn)
    check("DSN contains structure block",   "(structure" in dsn)
    check("DSN contains placement block",   "(placement" in dsn)
    check("DSN contains library block",     "(library" in dsn)
    check("DSN contains network block",     "(network" in dsn)
    check("DSN contains wiring block",      "(wiring" in dsn,
          detail="sample has pre-routed tracks")
    check("DSN contains F.Cu layer",        "F.Cu" in dsn)
    check("DSN contains B.Cu layer",        "B.Cu" in dsn)
    # Every footprint should have an image entry
    for fp in board["footprints"]:
        check(f"DSN library has image for {fp['ref']}",
              f"img_{fp['ref']}" in dsn)
    # Every distinct net should appear
    nets = set()
    for fp in board["footprints"]:
        for p in fp.get("pads", []):
            if p.get("net"): nets.add(p["net"])
    for n in nets:
        check(f"DSN network has net '{n}'", f'"{n}"' in dsn)
    # Sanity: bbox values should be present (in 0.1um since resolution=10)
    bbox = board["meta"]["board_bbox"]
    check("DSN boundary uses bbox lower-left",
          f'{int(bbox["x_min"]*10000)} {int(bbox["y_min"]*10000)}' in dsn)
    check("DSN boundary uses bbox upper-right",
          f'{int(bbox["x_max"]*10000)} {int(bbox["y_max"]*10000)}' in dsn)

    # ---- 2. SES s-expression parser ---------------------------------------
    sample_ses = """
    (session test_board
      (base_design "test_board.dsn")
      (placement (resolution um 10))
      (was_is)
      (routes
        (resolution um 10)
        (parser (host_cad "freerouting") (host_version "1.9.0"))
        (library_out (padstack Via_600_300))
        (network_out
          (net "VCC"
            (wire (path F.Cu 2500 10000 20000 30000 20000 50000 25000) (type route)))
          (net "GND"
            (wire (path B.Cu 5000 40000 60000 50000 60000) (type route))
            (via Via_600_300 40000 60000)))))
    """
    parsed = parse_sexpr(sample_ses)
    check("SES parser: top-level list", isinstance(parsed, list))
    check("SES parser: head is 'session'",
          parsed and parsed[0] == "session")

    result = parse_ses(sample_ses)
    check("SES gives tracks", isinstance(result.get("tracks"), list))
    check("SES gives vias",   isinstance(result.get("vias"), list))
    # VCC wire is a 3-point path -> 2 segments
    vcc_tracks = [t for t in result["tracks"] if t["net"] == "VCC"]
    check("SES VCC has 2 segments", len(vcc_tracks) == 2,
          detail=f"got {len(vcc_tracks)}")
    if vcc_tracks:
        t0 = vcc_tracks[0]
        check("SES VCC layer F.Cu",       t0["layer"] == "F.Cu")
        check("SES VCC width 0.25mm",     t0["width_mm"] == 0.25,
              detail=f"got {t0['width_mm']}")
        # Coords: 1000um -> 1.0mm, 2000um -> 2.0mm
        check("SES VCC start x=1.0mm",    t0["start"]["x_mm"] == 1.0)
        check("SES VCC start y=2.0mm",    t0["start"]["y_mm"] == 2.0)
    # GND wire 1 segment + 1 via
    gnd_tracks = [t for t in result["tracks"] if t["net"] == "GND"]
    gnd_vias   = [v for v in result["vias"]   if v["net"] == "GND"]
    check("SES GND has 1 segment", len(gnd_tracks) == 1,
          detail=f"got {len(gnd_tracks)}")
    check("SES GND has 1 via",     len(gnd_vias)   == 1,
          detail=f"got {len(gnd_vias)}")
    if gnd_vias:
        v = gnd_vias[0]
        check("SES GND via x=4.0mm", v["x_mm"] == 4.0)
        check("SES GND via y=6.0mm", v["y_mm"] == 6.0)

    # ---- 3. SES with no routes (empty network_out) ------------------------
    empty_ses = '(session b (routes (resolution um 10) (network_out)))'
    er = parse_ses(empty_ses)
    check("Empty SES yields no tracks", er["tracks"] == [])
    check("Empty SES yields no vias",   er["vias"]   == [])

    # ---- 4. Quoted strings with spaces in DSN preserved -------------------
    dsn2 = export_dsn({
        "meta": {"board_bbox": {"x_min": 0, "y_min": 0, "x_max": 10, "y_max": 10}},
        "footprints": [{
            "ref": "U1", "value": "MCU with space",
            "x_mm": 5, "y_mm": 5, "layer": "F.Cu", "rotation_deg": 0,
            "pads": [
                {"number": "1", "x_mm": 4, "y_mm": 5,
                 "size_mm": [1, 1], "shape": "rect", "net": "5V"},
                {"number": "2", "x_mm": 6, "y_mm": 5,
                 "size_mm": [1, 1], "shape": "rect", "net": "GND"},
            ],
        }],
    })
    check("DSN handles single footprint",  "img_U1" in dsn2)
    check("DSN has both nets",
          '"5V"' in dsn2 and '"GND"' in dsn2)

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("=== DSN/SES UNIT TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
