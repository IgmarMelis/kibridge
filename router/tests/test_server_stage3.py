"""
Stage 3 server endpoint tests.
Uses the same fake-Freerouting setup as test_route_engine, then exercises
/api/engines, /api/route, /api/route/status/<id>, /api/result,
/api/result/accept, and /api/drc.
"""
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "router"))

# Install the fake Freerouting BEFORE importing server
from test_route_engine import install_fake_freerouting
install_fake_freerouting()

from kirouter.server import create_app
from kirouter.state import state
from kirouter.router_engine import manager


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

    # ---- /api/engines ------------------------------------------------------
    r = client.get("/api/engines")
    check("GET /api/engines = 200", r.status_code == 200)
    d = r.get_json() or {}
    check("/api/engines lists freerouting",
          any(e["name"] == "freerouting" for e in d.get("engines", [])))

    # ---- /api/route requires a board --------------------------------------
    r = client.post("/api/route", json={})
    check("POST /api/route without board = 400", r.status_code == 400)

    # ---- POST a board first ------------------------------------------------
    sample_path = os.path.join(REPO_ROOT, "router", "kirouter",
                               "static", "sample_board.json")
    with open(sample_path) as f:
        sample = json.load(f)
    r = client.post("/api/board?source=test_stage3", json=sample)
    check("POST /api/board succeeds", r.status_code == 200)

    # ---- /api/route starts the job ----------------------------------------
    r = client.post("/api/route", json={"max_passes": 5})
    check("POST /api/route = 202", r.status_code == 202,
          detail=r.get_data(as_text=True))
    body = r.get_json() or {}
    check("response has job_id", isinstance(body.get("job_id"), str))
    job_id = body["job_id"]

    # ---- /api/route/status/<id> -------------------------------------------
    deadline = time.time() + 5
    final = None
    while time.time() < deadline:
        sr = client.get(f"/api/route/status/{job_id}")
        if sr.status_code != 200:
            break
        st = (sr.get_json() or {}).get("status", {})
        if st.get("status") in ("done", "failed"):
            final = st
            break
        time.sleep(0.1)
    check("job reached terminal status", final is not None)
    check("final status = done",         final and final.get("status") == "done",
          detail=str(final))

    # ---- /api/route/status (no id) returns the active job -----------------
    r = client.get("/api/route/status")
    check("GET /api/route/status = 200", r.status_code == 200)
    body = r.get_json() or {}
    check("active flag is True after run", body.get("active") is True)

    # ---- /api/result -------------------------------------------------------
    r = client.get("/api/result")
    check("GET /api/result = 200", r.status_code == 200)
    body = r.get_json() or {}
    check("/api/result has board",        "board" in body)
    check("/api/result has added_tracks", isinstance(body.get("added_tracks"), list))
    check("/api/result added 2 tracks (from fake)",
          len(body.get("added_tracks", [])) == 2)
    check("/api/result added 1 via",
          len(body.get("added_vias", [])) == 1)
    check("/api/result has elapsed",      isinstance(body.get("elapsed"), (int, float)))

    # ---- /api/result/accept -----------------------------------------------
    pre_info = (client.get("/api/info").get_json() or {})
    pre_track_count = pre_info.get("counts", {}).get("tracks", 0)
    r = client.post("/api/result/accept")
    check("POST /api/result/accept = 200", r.status_code == 200)
    post_info = r.get_json().get("info", {})
    post_tracks = post_info.get("counts", {}).get("tracks", 0)
    check("track count grew after accept",
          post_tracks > pre_track_count,
          detail=f"before={pre_track_count}, after={post_tracks}")
    check("source updated to routed-...",
          post_info.get("source", "").startswith("routed-"))

    # ---- /api/drc ----------------------------------------------------------
    r = client.post("/api/drc")
    check("POST /api/drc = 200", r.status_code == 200)
    d = r.get_json() or {}
    check("/api/drc has 'total'",      "total" in d)
    check("/api/drc has 'counts'",     "counts" in d)
    check("/api/drc has 'violations'", isinstance(d.get("violations"), list))

    # ---- DRC requires a board ---------------------------------------------
    state.clear()
    r = client.post("/api/drc")
    check("DRC with no board = 400", r.status_code == 400)

    # ---- /api/result requires an active completed job ---------------------
    # (After clearing state, the manager still has the job, but result
    #  endpoint returns the result; that's fine. Test the cleared-after-restart
    #  scenario by querying an unknown job id.)
    r = client.get("/api/route/status/zzzzzzzz")
    check("unknown job_id = 404", r.status_code == 404)

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("=== STAGE 3 SERVER TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
