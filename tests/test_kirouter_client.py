"""
Plugin -> KiRouter round-trip test.

We can't run inside KiCad in CI, so:
  1. We install a fake `pcbnew` module before the plugin imports it.
  2. We fake the KiRouter server with a Flask test client by monkey-
     patching urllib so HTTP calls go to the test client instead of a
     real socket.
  3. We exercise the full flow:
     build_board_json -> post_board -> (server has it) ->
     start route -> wait -> get_result -> apply_routes_to_board
     and check the fake pcbnew received the right add() calls.

Caught bugs along the way are fed back into kirouter_client.py.
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
from io import BytesIO


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "plugin"))
sys.path.insert(0, os.path.join(REPO_ROOT, "router"))
sys.path.insert(0, os.path.join(REPO_ROOT, "router", "tests"))


# ---- Fake pcbnew --------------------------------------------------------
class FakeVECTOR2I:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __repr__(self):
        return f"V({self.x},{self.y})"


class FakeNet:
    def __init__(self, name, code):
        self._name = name
        self._code = code

    def GetNetname(self):
        return self._name

    def GetNetCode(self):
        return self._code


class FakeNetInfo:
    def __init__(self, nets):
        self._nets = nets

    def GetNetCount(self):
        return len(self._nets)

    def GetNetItem(self, i):
        return self._nets[i]


class FakeTrack:
    def __init__(self, board):
        self._board = board
        self.start = None
        self.end = None
        self.width = 0
        self.layer = None
        self.net = None

    def SetStart(self, v): self.start = v
    def SetEnd(self, v):   self.end = v
    def SetWidth(self, w): self.width = w
    def SetLayer(self, l): self.layer = l
    def SetNet(self, n):   self.net = n


class FakeVia:
    def __init__(self, board):
        self._board = board
        self.position = None
        self.width = 0
        self.drill = 0
        self.net = None
        self.layers = None

    def SetPosition(self, v):     self.position = v
    def SetWidth(self, w):        self.width = w
    def SetDrill(self, d):        self.drill = d
    def SetNet(self, n):          self.net = n
    def SetLayerPair(self, a, b): self.layers = (a, b)


class FakeFootprint:
    def __init__(self, ref):
        self._ref = ref

    def GetPosition(self):
        return FakeVECTOR2I(0, 0)


class FakeBoardBBox:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def GetX(self):      return self.x
    def GetY(self):      return self.y
    def GetWidth(self):  return self.w
    def GetHeight(self): return self.h


class FakeBoard:
    def __init__(self):
        self._added = []  # records every Add() for assertions
        self._nets = [
            FakeNet("",      0),
            FakeNet("VCC",   1),
            FakeNet("GND",   2),
            FakeNet("FAKE_NET_A", 3),
            FakeNet("FAKE_NET_B", 4),
        ]
        self._filename = ""

    def Add(self, item):
        self._added.append(item)

    def GetNetInfo(self):
        return FakeNetInfo(self._nets)

    def GetFileName(self):
        return self._filename

    def GetFootprints(self):
        return []  # no real footprints needed for apply tests

    def GetBoardEdgesBoundingBox(self):
        # 100mm x 100mm board at origin (KiCad uses nm)
        return FakeBoardBBox(0, 0, 100_000_000, 100_000_000)


class _FakePcbnewModule(types.ModuleType):
    """A pcbnew module that returns a sentinel for any attribute we forgot."""
    _counter = [100]
    def __getattr__(self, name):
        # Return a unique int sentinel for unknown attrs (layer IDs etc.)
        self._counter[0] += 1
        v = self._counter[0]
        setattr(self, name, v)
        return v


def make_fake_pcbnew():
    mod = _FakePcbnewModule("pcbnew")
    mod.VECTOR2I = FakeVECTOR2I
    mod.PCB_TRACK = FakeTrack
    mod.PCB_VIA = FakeVia
    # Pin the copper layer ids we DO assert on in tests
    mod.F_Cu = 0
    mod.B_Cu = 31
    # API stubs
    mod.GetBuildVersion = lambda: "fake-10.0.1"
    mod.GetBoard = lambda: None
    mod.SaveBoard = lambda *a, **k: True
    mod.Refresh = lambda: None
    mod.FromMM = lambda mm: int(round(mm * 1_000_000))
    mod.ToMM = lambda nm: nm / 1_000_000

    class _AP:
        def register(self): pass
        def defaults(self): pass
    mod.ActionPlugin = _AP
    return mod


# Install BEFORE any plugin import
sys.modules["pcbnew"] = make_fake_pcbnew()

# Also need a fake wx so the plugin button modules can import (we don't
# call them in this test, but registration may pull them in transitively).
fake_wx = types.ModuleType("wx")
fake_wx.MessageBox = lambda *a, **k: 0
fake_wx.OK = 0; fake_wx.YES = 0; fake_wx.NO = 0
fake_wx.YES_NO = 0; fake_wx.ICON_INFORMATION = 0; fake_wx.ICON_ERROR = 0
fake_wx.ICON_WARNING = 0; fake_wx.ICON_QUESTION = 0
sys.modules["wx"] = fake_wx


# ---- Fake KiRouter server (Flask test client + urllib monkey-patch) ----
from test_route_engine import install_fake_freerouting
install_fake_freerouting()

from kirouter.server import create_app
from kirouter.state import state as kr_state

state_clear_func = kr_state.clear
state_clear_func()

server_app = create_app()
server_client = server_app.test_client()

# Monkey-patch urllib.request.urlopen so kirouter_client (plugin side)
# routes through the Flask test client instead of opening a real socket.
import urllib.request as _real_urlrequest
import urllib.error as _real_urlerror


class FakeResponse:
    """Minimal context-manager response wrapper, like urllib's."""
    def __init__(self, status, body_bytes):
        self.status = status
        self._body = body_bytes

    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self): return self._body


def fake_urlopen(req, timeout=None):
    if isinstance(req, str):
        url, method, data, headers = req, "GET", None, {}
    else:
        url     = req.full_url
        method  = req.get_method()
        data    = req.data
        headers = dict(req.header_items())

    # Strip host:port - test client wants just the path
    if "://" in url:
        path = "/" + url.split("/", 3)[3] if url.count("/") >= 3 else "/"
    else:
        path = url

    if method == "GET":
        rv = server_client.get(path)
    elif method == "POST":
        rv = server_client.post(path, data=data,
                                headers={"Content-Type":
                                         headers.get("Content-type",
                                         headers.get("Content-Type",
                                                     "application/json"))})
    elif method == "DELETE":
        rv = server_client.delete(path)
    else:
        raise NotImplementedError(method)

    if rv.status_code >= 400:
        raise _real_urlerror.HTTPError(
            url, rv.status_code, rv.status, {}, BytesIO(rv.data))
    return FakeResponse(rv.status_code, rv.data)


_real_urlrequest.urlopen = fake_urlopen


# ---- Now import the plugin modules under test ---------------------------
from kibridge import kirouter_client as client


def main() -> int:
    failures: list[str] = []

    def check(label, ok, *, detail=""):
        if ok:
            print(f"  OK   {label}")
        else:
            failures.append(label)
            print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")

    # ---- 1. base_url guards against non-local hosts -------------------
    try:
        client.base_url("8.8.8.8")
        check("non-local host blocked", False, detail="no exception")
    except ValueError:
        check("non-local host blocked", True)

    check("localhost allowed",
          client.base_url("127.0.0.1") == "http://127.0.0.1:8765")

    # ---- 2. is_server_up via test client ------------------------------
    up, detail = client.is_server_up()
    check("server health probe succeeds", up, detail=detail)
    check("health detail contains KiRouter",
          "KiRouter" in detail, detail=detail)

    # ---- 3. build_board_json from fake board --------------------------
    # The fake board has no footprints, so we need to inject one via
    # monkey-patching the helpers it pulls from workspace_exporter.
    board = FakeBoard()

    # We can't easily run the real _export_footprints_with_pads (depends
    # on pcbnew internals), so we monkey-patch the function in the client
    # module to return a fixed payload:
    from kibridge import kirouter_client as kc

    sample_footprints = [{
        "ref": "U1", "value": "MCU",
        "x_mm": 50, "y_mm": 50, "layer": "F.Cu", "rotation_deg": 0,
        "pads": [
            {"number": "1", "x_mm": 49, "y_mm": 50,
             "size_mm": [1.0, 1.0], "shape": "rect", "net": "VCC"},
            {"number": "2", "x_mm": 51, "y_mm": 50,
             "size_mm": [1.0, 1.0], "shape": "rect", "net": "GND"},
        ],
    }]
    kc._export_footprints_with_pads = lambda b: sample_footprints

    from kibridge import workspace_exporter as wxe
    wxe._export_tracks      = lambda b: {"tracks": [], "vias": []}
    wxe._export_design_rules = lambda b: {
        "design_settings": {"min_track_width_mm": 0.2,
                            "min_via_diameter_mm": 0.6,
                            "min_via_drill_mm": 0.3,
                            "min_clearance_mm": 0.2},
        "net_classes": []
    }

    board_json = client.build_board_json(board)
    check("build_board_json returns dict", isinstance(board_json, dict))
    check("schema has meta",        "meta"        in board_json)
    check("schema has footprints",  "footprints"  in board_json)
    check("schema has tracks",      "tracks"      in board_json)
    check("schema has vias",        "vias"        in board_json)
    check("schema has design_rules", "design_rules" in board_json)
    check("meta has board_bbox",
          "board_bbox" in board_json["meta"])
    bb = board_json["meta"]["board_bbox"]
    # New behavior (>=v1.0.5): bbox includes 10mm margin around everything.
    # The fake board reports 100mm x 100mm edges + footprint at (0,0)
    # so result is (0-10) to (100+10) = 120mm span.
    check("bbox has 10mm margin around content",
          bb["x_max"] - bb["x_min"] == 120.0 and bb["y_max"] - bb["y_min"] == 120.0,
          detail=f"got {bb}")

    # ---- 4. post_board succeeds ---------------------------------------
    resp = client.post_board(board_json)
    check("post_board returns ok=True", resp.get("ok") is True)
    check("post_board info.source = kibridge",
          (resp.get("info") or {}).get("source") == "kibridge")

    # ---- 5. get_info reflects what we posted --------------------------
    info = client.get_info()
    check("get_info shows loaded", info.get("loaded") is True)
    check("get_info counts footprints == 1",
          info.get("counts", {}).get("footprints") == 1)

    # ---- 6. Trigger a route via the server ----------------------------
    # We hit /api/route directly through the test client.
    r = server_client.post("/api/route", json={"max_passes": 5})
    check("POST /api/route accepted", r.status_code == 202)
    job_id = r.get_json()["job_id"]

    deadline = time.time() + 5
    while time.time() < deadline:
        rs = server_client.get(f"/api/route/status/{job_id}").get_json()
        if rs["status"]["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    check("job completes", rs["status"]["status"] == "done",
          detail=str(rs))

    # ---- 7. get_result via plugin client -----------------------------
    result = client.get_result()
    check("get_result returns payload", result is not None)
    check("result has added_tracks",
          isinstance(result.get("added_tracks"), list))
    check("result has 2 tracks (fake JAR)",
          len(result.get("added_tracks", [])) == 2)
    check("result has 1 via",
          len(result.get("added_vias", [])) == 1)

    # ---- 8. get_result returns None when no result -------------------
    # Clear server state and re-test
    state_clear_func()
    # Need to reset the manager's _active_id too so /api/result misses cleanly
    from kirouter.router_engine import manager
    manager._active_id = None
    r2 = client.get_result()
    check("get_result returns None when no result", r2 is None)

    # ---- 9. apply_routes_to_board adds to FakeBoard -------------------
    fresh_board = FakeBoard()
    added_tracks = [
        {"net": "FAKE_NET_A", "layer": "F.Cu", "width_mm": 0.25,
         "start": {"x_mm": 5,  "y_mm": 5},
         "end":   {"x_mm": 6,  "y_mm": 5}},
        {"net": "FAKE_NET_B", "layer": "B.Cu", "width_mm": 0.5,
         "start": {"x_mm": 7,  "y_mm": 7},
         "end":   {"x_mm": 8,  "y_mm": 7}},
    ]
    added_vias = [
        {"net": "FAKE_NET_A", "x_mm": 7.5, "y_mm": 5,
         "width_mm": 0.6, "drill_mm": 0.3},
    ]
    summary = client.apply_routes_to_board(
        fresh_board, added_tracks, added_vias)

    check("apply added 2 tracks",
          summary["tracks_added"] == 2,
          detail=str(summary))
    check("apply added 1 via",
          summary["vias_added"] == 1,
          detail=str(summary))
    check("apply errors empty",
          summary["errors"] == [],
          detail=str(summary["errors"]))
    check("FakeBoard received 3 Add() calls",
          len(fresh_board._added) == 3)

    # Check the tracks have the right coordinates (in nm)
    tracks_in_board = [x for x in fresh_board._added if isinstance(x, FakeTrack)]
    check("first track at correct start (5mm -> 5_000_000 nm)",
          tracks_in_board[0].start.x == 5_000_000
          and tracks_in_board[0].start.y == 5_000_000)
    check("first track width 0.25mm = 250000 nm",
          tracks_in_board[0].width == 250_000,
          detail=f"got {tracks_in_board[0].width}")
    check("first track layer F.Cu",
          tracks_in_board[0].layer == 0)
    check("second track layer B.Cu",
          tracks_in_board[1].layer == 31)
    check("first track net = FAKE_NET_A",
          tracks_in_board[0].net.GetNetname() == "FAKE_NET_A")

    vias_in_board = [x for x in fresh_board._added if isinstance(x, FakeVia)]
    check("via position correct",
          vias_in_board[0].position.x == 7_500_000
          and vias_in_board[0].position.y == 5_000_000)
    check("via width 0.6mm",
          vias_in_board[0].width == 600_000)
    check("via drill 0.3mm",
          vias_in_board[0].drill == 300_000)
    check("via spans F.Cu to B.Cu",
          vias_in_board[0].layers == (0, 31))

    # ---- 10. apply skips tracks with unknown nets gracefully ----------
    board2 = FakeBoard()
    bad_tracks = [
        {"net": "NONEXISTENT_NET", "layer": "F.Cu", "width_mm": 0.25,
         "start": {"x_mm": 1, "y_mm": 1}, "end": {"x_mm": 2, "y_mm": 1}},
        {"net": "VCC", "layer": "F.Cu", "width_mm": 0.25,
         "start": {"x_mm": 1, "y_mm": 1}, "end": {"x_mm": 2, "y_mm": 1}},
    ]
    summary2 = client.apply_routes_to_board(board2, bad_tracks, [])
    check("unknown-net track skipped not crashed",
          summary2["tracks_added"] == 1)
    check("error recorded for unknown net",
          any("unknown net" in e for e in summary2["errors"]))

    # ---- 11. backup_board_file -----------------------------------------
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "demo.kicad_pcb")
        with open(src, "w") as f:
            f.write("(kicad_pcb (version 20240101))")
        backup_path = client.backup_board_file(src)
        check("backup created", os.path.isfile(backup_path))
        check("backup name uses kibridge_backup_ prefix",
              os.path.basename(backup_path).startswith("kibridge_backup_"))
        check("backup contents match",
              open(backup_path).read() == "(kicad_pcb (version 20240101))")

    # ---- 12. backup raises on missing file ----------------------------
    try:
        client.backup_board_file("/nonexistent/path.kicad_pcb")
        check("backup raises on missing", False)
    except FileNotFoundError:
        check("backup raises on missing", True)

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("=== STAGE 4 PLUGIN CLIENT TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
