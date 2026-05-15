"""
KiRouter server round-trip test.

Uses Flask's test client (no live socket) so it's safe in CI and doesn't
collide with any other process that might be using port 8765.

Verifies:
  - /api/health returns the product info
  - /api/info reports an empty board initially
  - POST /api/board accepts a valid board
  - POST /api/board rejects malformed input (missing fields, wrong content type)
  - GET /api/board echoes back what was uploaded
  - DELETE /api/board clears state
  - source query param is honoured
"""
import json
import os
import sys


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROUTER_PKG = os.path.join(REPO_ROOT, "router")

sys.path.insert(0, ROUTER_PKG)

from kirouter.server import create_app
from kirouter.state import state


def main() -> int:
    state.clear()
    app = create_app()
    client = app.test_client()
    failures = []

    def check(label, ok, *, detail=""):
        if ok:
            print(f"  OK   {label}")
        else:
            failures.append(label)
            print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")

    # 1. Health
    r = client.get("/api/health")
    check("health endpoint 200",  r.status_code == 200)
    d = r.get_json() or {}
    check("health.ok = True",     d.get("ok") is True)
    check("health.product correct", d.get("product") == "KiRouter",
          detail=f"got {d.get('product')!r}")
    check("health.company correct", d.get("company") == "PSS Tools")
    check("health.version present", isinstance(d.get("version"), str))

    # 2. Info on empty
    r = client.get("/api/info")
    check("info empty 200",       r.status_code == 200)
    d = r.get_json() or {}
    check("info.loaded = False",  d.get("loaded") is False)

    # 3. Get board on empty -> 404
    r = client.get("/api/board")
    check("get empty board 404",  r.status_code == 404)

    # 4. POST without JSON content type -> 400
    r = client.post("/api/board", data="not json")
    check("post non-json 400",    r.status_code == 400)

    # 5. POST with missing fields -> 400
    r = client.post("/api/board", json={"meta": {}})
    check("post missing footprints 400", r.status_code == 400)

    # 6. POST a valid board
    sample_path = os.path.join(REPO_ROOT, "router", "kirouter",
                               "static", "sample_board.json")
    with open(sample_path, "r", encoding="utf-8") as f:
        sample = json.load(f)
    r = client.post("/api/board?source=test", json=sample)
    check("post sample board 200", r.status_code == 200,
          detail=r.get_data(as_text=True))
    posted = r.get_json() or {}
    check("post.ok",               posted.get("ok") is True)
    info = posted.get("info") or {}
    check("info.loaded after post", info.get("loaded") is True)
    check("info.source = test",     info.get("source") == "test")
    counts = info.get("counts") or {}
    check("footprint count = 6",    counts.get("footprints") == 6)
    check("track count = 7",        counts.get("tracks") == 7)
    check("via count = 2",          counts.get("vias") == 2)
    # nets in sample: VCC, GND, RST, PB0, PB1, PB2, PB3, PB4, LED_A = 9
    check("net count = 9",          counts.get("nets") == 9,
          detail=f"got {counts.get('nets')}")

    # 7. GET the board back
    r = client.get("/api/board")
    check("get board 200",          r.status_code == 200)
    got = r.get_json() or {}
    check("round-trip footprints", got.get("footprints") == sample["footprints"])
    check("round-trip tracks",     got.get("tracks")     == sample["tracks"])
    check("round-trip vias",       got.get("vias")       == sample["vias"])

    # 8. Static UI is served
    r = client.get("/")
    check("index.html served",      r.status_code == 200 and b"KiRouter" in r.data)
    r = client.get("/static/style.css")
    check("style.css served",       r.status_code == 200)
    r = client.get("/static/canvas.js")
    check("canvas.js served",       r.status_code == 200)
    r = client.get("/static/app.js")
    check("app.js served",          r.status_code == 200)
    r = client.get("/static/sample_board.json")
    check("sample_board.json served", r.status_code == 200)

    # 9. DELETE clears
    r = client.delete("/api/board")
    check("delete 200",             r.status_code == 200)
    r = client.get("/api/info")
    info2 = r.get_json() or {}
    check("info.loaded after delete = False", info2.get("loaded") is False)

    # 10. Bind-host guard test: server.main() refuses 0.0.0.0
    from kirouter.server import main as server_main
    rc = server_main(["--host", "0.0.0.0", "--port", "1"])
    check("refuses to bind to 0.0.0.0", rc == 2)

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("=== KIROUTER ROUND-TRIP PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
