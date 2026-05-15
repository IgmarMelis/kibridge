"""Unit tests for kirouter.drc.run_drc."""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "router"))

from kirouter.drc import run_drc


def board_with(rules, footprints=None, tracks=None, vias=None, bbox=None):
    return {
        "meta": {"board_bbox": bbox or {"x_min": 0, "y_min": 0,
                                         "x_max": 100, "y_max": 100}},
        "design_rules": {"design_settings": rules},
        "footprints": footprints or [],
        "tracks":     tracks or [],
        "vias":       vias or [],
    }


def fp(ref, x, y, pads):
    return {"ref": ref, "value": "?", "x_mm": x, "y_mm": y,
            "layer": "F.Cu", "rotation_deg": 0, "pads": pads}


def pad(num, x, y, net, sx=1.0, sy=1.0, shape="rect"):
    return {"number": num, "x_mm": x, "y_mm": y,
            "size_mm": [sx, sy], "shape": shape, "net": net}


def trk(net, layer, w, sx, sy, ex, ey):
    return {"net": net, "layer": layer, "width_mm": w, "length_mm": 0,
            "start": {"x_mm": sx, "y_mm": sy},
            "end":   {"x_mm": ex, "y_mm": ey}}


def via(net, x, y, w=0.6, d=0.3):
    return {"net": net, "x_mm": x, "y_mm": y,
            "width_mm": w, "drill_mm": d}


def main() -> int:
    failures = []

    def check(label, ok, *, detail=""):
        if ok:
            print(f"  OK   {label}")
        else:
            failures.append(label)
            print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")

    # ---- 1. Track narrower than minimum ------------------------------------
    rules = {"min_track_width_mm": 0.3, "min_clearance_mm": 0.2,
             "min_via_diameter_mm": 0.5, "min_via_drill_mm": 0.3}
    b = board_with(rules, tracks=[trk("VCC", "F.Cu", 0.2, 10, 10, 20, 10)])
    v = run_drc(b)
    codes = [x["code"] for x in v]
    check("track_width_below_min fires when track too narrow",
          "track_width_below_min" in codes)

    # ---- 2. Track at minimum width is OK ----------------------------------
    b = board_with(rules, tracks=[trk("VCC", "F.Cu", 0.3, 10, 10, 20, 10)])
    v = run_drc(b)
    check("no track_width violation at exact minimum",
          all(x["code"] != "track_width_below_min" for x in v))

    # ---- 3. Via drill / diameter below min --------------------------------
    b = board_with(rules, vias=[via("GND", 50, 50, w=0.4, d=0.2)])
    codes = [x["code"] for x in run_drc(b)]
    check("via_diameter_below_min fires", "via_diameter_below_min" in codes)
    check("via_drill_below_min fires",     "via_drill_below_min" in codes)

    # ---- 4. Track outside board outline -----------------------------------
    b = board_with(rules,
                   bbox={"x_min": 0, "y_min": 0, "x_max": 50, "y_max": 50},
                   tracks=[trk("SIG", "F.Cu", 0.4, 10, 10, 60, 10)])  # ends past 50
    codes = [x["code"] for x in run_drc(b)]
    check("track_outside_board fires", "track_outside_board" in codes)

    # ---- 5. Track-pad short ------------------------------------------------
    b = board_with(rules,
                   footprints=[fp("U1", 0, 0, [
                       pad("1", 10, 10, "VCC", sx=2, sy=2),  # large pad on VCC
                   ])],
                   tracks=[trk("GND", "F.Cu", 0.4, 10.1, 10.1, 30, 30)])
    codes = [x["code"] for x in run_drc(b)]
    check("track_pad_short fires when track endpoint over wrong-net pad",
          "track_pad_short" in codes)

    # ---- 6. Track-track clearance violation -------------------------------
    b = board_with(rules, tracks=[
        trk("A", "F.Cu", 0.3, 0, 10, 10, 10),
        trk("B", "F.Cu", 0.3, 0, 10.05, 10, 10.05),  # parallel, very close
    ])
    codes = [x["code"] for x in run_drc(b)]
    check("track_track_clearance fires when too close",
          "track_track_clearance" in codes)

    # ---- 7. Same net is exempt from clearance check -----------------------
    b = board_with(rules, tracks=[
        trk("VCC", "F.Cu", 0.3, 0, 10, 10, 10),
        trk("VCC", "F.Cu", 0.3, 0, 10.05, 10, 10.05),
    ])
    codes = [x["code"] for x in run_drc(b)]
    check("same-net tracks do NOT trigger clearance violation",
          "track_track_clearance" not in codes)

    # ---- 8. Different layers exempt from clearance ------------------------
    b = board_with(rules, tracks=[
        trk("A", "F.Cu", 0.3, 0, 10, 10, 10),
        trk("B", "B.Cu", 0.3, 0, 10.05, 10, 10.05),  # close BUT different layer
    ])
    codes = [x["code"] for x in run_drc(b)]
    check("different-layer tracks do NOT trigger clearance violation",
          "track_track_clearance" not in codes)

    # ---- 9. Clean board returns no violations -----------------------------
    b = board_with(rules,
                   footprints=[fp("U1", 50, 50, [pad("1", 50, 50, "VCC")])],
                   tracks=[trk("VCC", "F.Cu", 0.5, 50, 50, 60, 50)])
    v = run_drc(b)
    check("clean board has 0 violations", v == [],
          detail=f"got {len(v)}: {[x['code'] for x in v]}")

    # ---- 10. Result rows have all required keys --------------------------
    b = board_with(rules, tracks=[trk("VCC", "F.Cu", 0.1, 10, 10, 20, 10)])
    v = run_drc(b)
    if v:
        row = v[0]
        for k in ("code", "level", "msg", "x_mm", "y_mm", "layer", "nets"):
            check(f"violation has '{k}' key", k in row,
                  detail=f"got keys {list(row.keys())}")

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("=== DRC UNIT TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
