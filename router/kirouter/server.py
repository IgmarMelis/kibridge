"""
KiRouter HTTP server.

Stage 2 endpoints (board state):
  GET    /api/health                 liveness probe
  GET    /api/info                   info about the loaded board
  GET    /api/board                  current board state (full)
  POST   /api/board                  upload/replace the board state
  DELETE /api/board                  clear current state

Stage 3 endpoints (routing + DRC):
  GET    /api/engines                list available engines + availability
  POST   /api/route                  start a routing job
  GET    /api/route/status           status of the active job
  GET    /api/route/status/<id>      status of a specific job
  POST   /api/route/cancel           cancel the active job (no-op once running)
  GET    /api/result                 the routed board (only when job is done)
  POST   /api/result/accept          replace board state with the route result
  POST   /api/drc                    compute DRC violations on current board

Stage 4 (planned):
  POST   /api/export/kibridge        package result for KiBridge import
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser

from flask import Flask, jsonify, request, send_from_directory, abort

from . import __version__, __product__, __company__
from .state  import state
from .drc    import run_drc
from .router_engine import (
    manager, RouteOptions, list_engines, get_engine,
)


HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 8765

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")

    # ---- UI -----------------------------------------------------------------
    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    # ---- Health & info ------------------------------------------------------
    @app.route("/api/health")
    def health():
        return jsonify({
            "ok":      True,
            "product": __product__,
            "company": __company__,
            "version": __version__,
        })

    @app.route("/api/info")
    def info():
        return jsonify(state.info())

    # ---- Board state --------------------------------------------------------
    @app.route("/api/board", methods=["GET"])
    def get_board():
        b = state.get()
        if b is None:
            abort(404, description="No board loaded.")
        return jsonify(b)

    @app.route("/api/board", methods=["POST"])
    def post_board():
        if not request.is_json:
            abort(400, description="Content-Type must be application/json")
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400, description="Body must be a JSON object")
        for key in ("meta", "footprints"):
            if key not in data:
                abort(400, description=f"Missing required key: '{key}'")
        if not isinstance(data.get("footprints"), list):
            abort(400, description="'footprints' must be a list")

        source = request.args.get("source", "api")
        state.set(data, source=source)
        return jsonify({
            "ok":          True,
            "received_at": time.time(),
            "info":        state.info(),
        })

    @app.route("/api/board", methods=["DELETE"])
    def delete_board():
        state.clear()
        return jsonify({"ok": True})

    # ---- Engines ------------------------------------------------------------
    @app.route("/api/engines")
    def engines():
        return jsonify({"engines": list_engines()})

    # ---- Route job lifecycle ------------------------------------------------
    @app.route("/api/route", methods=["POST"])
    def start_route():
        board = state.get()
        if board is None:
            abort(400, description="No board loaded. POST /api/board first.")

        body = request.get_json(silent=True) or {}
        opts = RouteOptions(
            max_passes      = int(body.get("max_passes", 30)),
            timeout_seconds = float(body.get("timeout_seconds", 600.0)),
            engine          = str(body.get("engine", "freerouting")),
        )

        # Pre-flight: refuse with a useful error if the engine isn't available.
        try:
            engine = get_engine(opts.engine)
        except KeyError as e:
            abort(400, description=str(e))
        avail = engine.is_available()
        if not avail.get("ok"):
            return jsonify({
                "ok": False,
                "error": "engine not available",
                "engine": opts.engine,
                "details": avail,
            }), 503

        try:
            job = manager.submit(board, opts)
        except RuntimeError as e:
            return jsonify({"ok": False, "error": str(e)}), 409

        return jsonify({
            "ok":     True,
            "job_id": job.job_id,
            "status": manager.to_status_dict(job),
        }), 202

    @app.route("/api/route/status")
    def route_status_active():
        job = manager.active()
        if job is None:
            return jsonify({"ok": True, "active": False})
        return jsonify({
            "ok":     True,
            "active": True,
            "status": manager.to_status_dict(job),
        })

    @app.route("/api/route/status/<job_id>")
    def route_status(job_id):
        job = manager.get(job_id)
        if job is None:
            abort(404, description=f"unknown job_id: {job_id}")
        return jsonify({"ok": True, "status": manager.to_status_dict(job)})

    @app.route("/api/result")
    def get_result():
        job = manager.active()
        if job is None or job.result is None:
            abort(404, description="No completed route result available")
        return jsonify({
            "ok":            True,
            "engine":        job.result.engine,
            "elapsed":       job.result.elapsed_seconds,
            "added_tracks":  job.result.added_tracks,
            "added_vias":    job.result.added_vias,
            "board":         job.result.board,
        })

    @app.route("/api/result/accept", methods=["POST"])
    def accept_result():
        """Replace the live board state with the route result."""
        job = manager.active()
        if job is None or job.result is None:
            abort(404, description="No completed route result to accept")
        state.set(job.result.board, source=f"routed-{job.result.engine}")
        return jsonify({"ok": True, "info": state.info()})

    # ---- DRC ----------------------------------------------------------------
    @app.route("/api/drc", methods=["POST"])
    def post_drc():
        board = state.get()
        if board is None:
            abort(400, description="No board loaded.")
        violations = run_drc(board)
        by_level = {"error": 0, "warning": 0, "info": 0}
        for v in violations:
            by_level[v.get("level", "info")] = by_level.get(v.get("level", "info"), 0) + 1
        return jsonify({
            "ok":         True,
            "counts":     by_level,
            "total":      len(violations),
            "violations": violations,
        })

    # ---- Errors --------------------------------------------------------------
    @app.errorhandler(400)
    def err_400(e):
        return jsonify({"ok": False, "error": str(e.description)}), 400

    @app.errorhandler(404)
    def err_404(e):
        return jsonify({"ok": False, "error": str(e.description)}), 404

    return app


def _open_browser_after(host: str, port: int, delay: float = 0.6) -> None:
    def _go():
        time.sleep(delay)
        try:
            webbrowser.open_new_tab(f"http://{host}:{port}")
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kirouter",
                                     description=f"{__product__} v{__version__}")
    parser.add_argument("--host", default=HOST_DEFAULT,
                        help="bind host (default 127.0.0.1; do not bind to 0.0.0.0)")
    parser.add_argument("--port", type=int, default=PORT_DEFAULT,
                        help="bind port (default 8765)")
    parser.add_argument("--no-browser", action="store_true",
                        help="don't auto-open a browser tab")
    parser.add_argument("--debug", action="store_true",
                        help="run Flask in debug mode")
    args = parser.parse_args(argv)

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"refusing to bind to {args.host!r} — KiRouter is local-only.",
              file=sys.stderr)
        return 2

    app = create_app()

    print()
    print(f"  {__product__} v{__version__}  — by {__company__}")
    print(f"  Listening on http://{args.host}:{args.port}")
    print(f"  Static dir : {STATIC_DIR}")
    print(f"  Press Ctrl+C to stop.")
    print()

    if not args.no_browser:
        _open_browser_after(args.host, args.port)

    app.run(host=args.host, port=args.port, debug=args.debug,
            use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
