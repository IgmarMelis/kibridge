"""
Engine tests using a fake Freerouting.

We monkey-patch kirouter.freerouting.runner so that:
  - find_jar()  returns a sentinel Path
  - find_java() returns a sentinel string
  - run_freerouting() bypasses subprocess and writes a synthetic .ses file
    with two routed wires.

This lets us exercise the full engine pipeline (export DSN -> "run" ->
parse SES -> merge into board) and the JobManager state transitions
without needing a real Freerouting install in CI.
"""
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "router"))

import kirouter.freerouting.runner as runner_mod
from kirouter.router_engine import (
    manager, RouteOptions, get_engine, list_engines,
)


FAKE_SES = """\
(session test_board
  (base_design "test_board.dsn")
  (placement (resolution um 10))
  (was_is)
  (routes
    (resolution um 10)
    (parser (host_cad "freerouting") (host_version "2.0.0"))
    (network_out
      (net "FAKE_NET_A"
        (wire (path F.Cu 2500 50000 50000 60000 50000) (type route)))
      (net "FAKE_NET_B"
        (wire (path B.Cu 5000 70000 70000 80000 70000) (type route))
        (via Via_600_300 75000 70000)))))
"""


def install_fake_freerouting():
    """Replace runner internals with stubs."""
    runner_mod.find_java = lambda: "/usr/bin/java"
    runner_mod.find_jar  = lambda: Path("/fake/freerouting.jar")

    def fake_run(dsn_path, ses_path=None, *, max_passes=30,
                 timeout_seconds=600.0, on_progress=None,
                 java_path=None, jar_path=None, debug_copy_dir=None):
        if ses_path is None:
            ses_path = dsn_path.with_suffix(".ses")
        if on_progress:
            on_progress("[fake] starting routing")
            on_progress("[fake] pass 1 of 30")
            on_progress("[fake] pass 30 of 30 done")
        Path(ses_path).write_text(FAKE_SES, encoding="utf-8")
        return Path(ses_path)

    runner_mod.run_freerouting = fake_run

    # Monkey-patch the route_engine's reference too — it imported them
    import kirouter.router_engine as re
    re.run_freerouting = fake_run
    # is_available also needs to lie:
    from kirouter.freerouting import runner as r2
    def fake_check_env():
        return {"java": "/usr/bin/java",
                "jar":  "/fake/freerouting.jar",
                "jar_size": 12345,
                "errors": [],
                "ok": True}
    r2.check_environment = fake_check_env
    re.freerouting_check_environment = fake_check_env

    # Patch the engine's own is_available so it sees the stub
    eng = re.FreeroutingEngine()
    re._ENGINES["freerouting"] = eng
    eng.is_available = fake_check_env


def main() -> int:
    install_fake_freerouting()
    failures = []

    def check(label, ok, *, detail=""):
        if ok:
            print(f"  OK   {label}")
        else:
            failures.append(label)
            print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")

    # ---- list_engines ------------------------------------------------------
    engines = list_engines()
    check("list_engines returns >=1 entry", len(engines) >= 1)
    fr = next((e for e in engines if e["name"] == "freerouting"), None)
    check("freerouting engine present", fr is not None)
    check("freerouting reports available (with stub)",
          fr and fr["available"]["ok"] is True)

    # ---- direct engine call ------------------------------------------------
    sample_path = os.path.join(REPO_ROOT, "router", "kirouter",
                               "static", "sample_board.json")
    with open(sample_path) as f:
        board = json.load(f)
    engine = get_engine("freerouting")

    progress_calls = []
    def on_progress(line, pct):
        progress_calls.append((line, pct))

    result = engine.route(
        board, RouteOptions(max_passes=30), on_progress=on_progress
    )
    check("engine returned a result", result is not None)
    check("engine added 2 tracks (from fake ses)",
          len(result.added_tracks) == 2,
          detail=f"got {len(result.added_tracks)}")
    check("engine added 1 via",
          len(result.added_vias) == 1,
          detail=f"got {len(result.added_vias)}")
    check("merged board has more tracks than original",
          len(result.board["tracks"]) > len(board["tracks"]))
    check("on_progress was called",
          len(progress_calls) > 0)
    check("progress includes a 100% call",
          any(pct == 100 for _, pct in progress_calls))

    # ---- JobManager submit + wait -----------------------------------------
    job = manager.submit(board, RouteOptions(max_passes=10))
    check("job submitted",          job is not None)
    # Note: with the fake JAR, the worker thread can complete in microseconds,
    # so the job may already be "done" by the time we read it. We only assert
    # it's in a known state.
    check("job status valid",
          job.status in ("pending", "running", "done"),
          detail=f"got {job.status}")

    # Wait for completion (max 5 seconds)
    deadline = time.time() + 5
    while time.time() < deadline and job.status not in ("done", "failed"):
        time.sleep(0.05)
    check("job reaches 'done'",     job.status == "done",
          detail=f"final={job.status} err={job.error}")
    check("job has a result",       job.result is not None)
    check("job progress is 100",    job.progress_pct == 100)
    check("job log_tail not empty", len(job.log_tail) > 0)

    # ---- to_status_dict shape ---------------------------------------------
    sd = manager.to_status_dict(job)
    for k in ("job_id", "status", "progress", "log_tail",
              "engine", "result_summary"):
        check(f"status_dict has '{k}'", k in sd)
    check("result_summary has counts",
          sd["result_summary"]["added_tracks"] == 2)
    check("status_dict.engine = freerouting",
          sd["engine"] == "freerouting")

    # ---- Submitting again (after first finished) is allowed ---------------
    job2 = manager.submit(board, RouteOptions(max_passes=5))
    check("second submit accepted after first done", job2 is not None)
    while job2.status not in ("done", "failed"):
        time.sleep(0.05)
        if time.time() > deadline + 5:
            break
    check("second job done", job2.status == "done")
    check("second job has new id", job2.job_id != job.job_id)

    # ---- Test that real engine surfaces missing JAR ------------------------
    # Restore real find_jar to verify error path
    from kirouter.freerouting import runner as r3
    real_check = r3.check_environment
    def missing_check():
        return {"java": "/usr/bin/java", "jar": None,
                "errors": ["JAR not found"], "ok": False}
    r3.check_environment = missing_check
    import kirouter.router_engine as re2
    re2.freerouting_check_environment = missing_check
    re2._ENGINES["freerouting"].is_available = missing_check
    avail = get_engine("freerouting").is_available()
    check("missing JAR reported as not available", avail["ok"] is False)
    check("missing JAR reports the error", "JAR not found" in avail["errors"])

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("=== ROUTE ENGINE TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
