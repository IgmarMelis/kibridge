"""
router_engine — the abstraction every routing backend implements.

Today: one engine, FreeroutingEngine. Tomorrow (Stage 4+): a custom
PythonAStarEngine that lives next to it under the same interface.

The server only talks to this layer. Adding a new backend means writing
a new file here and registering it; nothing in server.py has to change.
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from kirouter.freerouting import (
    export_dsn, parse_ses, run_freerouting,
    check_environment as freerouting_check_environment,
    FreeroutingNotFound, JavaNotFound, FreeroutingFailed,
)


# ---- public types ----------------------------------------------------------
@dataclass
class RouteOptions:
    max_passes: int = 30
    timeout_seconds: float = 600.0
    engine: str = "freerouting"


@dataclass
class RouteResult:
    """The output of a routing run, applied on top of the input board."""
    board: dict          # full board JSON, with new tracks/vias appended
    added_tracks: list   # only the new tracks (for diff display)
    added_vias: list     # only the new vias
    log_lines: list[str] # full stdout/stderr capture from the engine
    engine: str
    elapsed_seconds: float


@dataclass
class JobState:
    job_id: str
    status: str = "pending"   # pending | running | done | failed | cancelled
    progress_pct: float = 0.0
    log_tail: list[str] = field(default_factory=list)
    error: str | None = None
    result: RouteResult | None = None
    started_at: float | None = None
    finished_at: float | None = None
    options: RouteOptions | None = None


# ---- engine interface ------------------------------------------------------
class Engine(Protocol):
    name: str

    def is_available(self) -> dict:
        ...

    def route(
        self,
        board: dict,
        options: RouteOptions,
        on_progress: Callable[[str, float], None],
    ) -> RouteResult:
        ...


# ---- freerouting engine ----------------------------------------------------
class FreeroutingEngine:
    name = "freerouting"

    def is_available(self) -> dict:
        return freerouting_check_environment()

    def route(
        self,
        board: dict,
        options: RouteOptions,
        on_progress: Callable[[str, float], None],
    ) -> RouteResult:
        started = time.time()
        with tempfile.TemporaryDirectory(prefix="kirouter_") as tmpdir:
            dsn_path = Path(tmpdir) / "board.dsn"
            ses_path = Path(tmpdir) / "board.ses"

            on_progress("exporting DSN...", 5)
            dsn_text = export_dsn(board)
            dsn_path.write_text(dsn_text, encoding="utf-8")
            on_progress(f"DSN written: {dsn_path.stat().st_size} bytes", 10)

            log_lines: list[str] = []
            total_passes = max(1, options.max_passes)
            current_pass = [0]   # closure mutable

            def cap(line: str) -> None:
                log_lines.append(line)
                # Best-effort progress: count "pass" lines in the freerouting log
                low = line.lower()
                if "pass" in low and any(c.isdigit() for c in low):
                    current_pass[0] += 1
                    pct = 10 + min(80, 80 * current_pass[0] / total_passes)
                    on_progress(line, pct)
                else:
                    on_progress(line, None)

            run_freerouting(
                dsn_path,
                ses_path,
                max_passes=options.max_passes,
                timeout_seconds=options.timeout_seconds,
                on_progress=cap,
                debug_copy_dir=Path.home() / ".kirouter" / "debug",
            )

            on_progress("parsing SES...", 92)
            ses_text = ses_path.read_text(encoding="utf-8", errors="replace")
            parsed = parse_ses(ses_text, reference_board=board)
            new_tracks = parsed.get("tracks", [])
            new_vias   = parsed.get("vias",   [])

        # Merge: keep original tracks/vias, append new ones.
        out_board = json.loads(json.dumps(board))   # deep copy
        out_board.setdefault("tracks", []).extend(new_tracks)
        out_board.setdefault("vias",   []).extend(new_vias)

        on_progress(
            f"merged: +{len(new_tracks)} tracks, +{len(new_vias)} vias",
            100,
        )
        return RouteResult(
            board=out_board,
            added_tracks=new_tracks,
            added_vias=new_vias,
            log_lines=log_lines,
            engine=self.name,
            elapsed_seconds=round(time.time() - started, 2),
        )


# ---- registry --------------------------------------------------------------
_ENGINES: dict[str, Engine] = {
    "freerouting": FreeroutingEngine(),
}


def get_engine(name: str) -> Engine:
    if name not in _ENGINES:
        raise KeyError(
            f"unknown engine '{name}'. Available: {list(_ENGINES)}")
    return _ENGINES[name]


def list_engines() -> list[dict]:
    out = []
    for name, eng in _ENGINES.items():
        out.append({"name": name, "available": eng.is_available()})
    return out


# ---- job manager -----------------------------------------------------------
class JobManager:
    """Holds the (single) currently-running route job, tracks status."""

    LOG_TAIL_MAX = 80

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, JobState] = {}
        self._active_id: str | None = None

    def submit(self, board: dict, options: RouteOptions) -> JobState:
        with self._lock:
            if self._active_id is not None:
                active = self._jobs.get(self._active_id)
                if active and active.status in ("pending", "running"):
                    raise RuntimeError(
                        f"a job is already {active.status} "
                        f"(id={self._active_id})")
            job = JobState(
                job_id=uuid.uuid4().hex[:12],
                status="pending",
                options=options,
            )
            self._jobs[job.job_id] = job
            self._active_id = job.job_id

        threading.Thread(
            target=self._run, args=(job, board), daemon=True
        ).start()
        return job

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active(self) -> JobState | None:
        with self._lock:
            return self._jobs.get(self._active_id) if self._active_id else None

    def to_status_dict(self, job: JobState) -> dict:
        return {
            "job_id":      job.job_id,
            "status":      job.status,
            "progress":    round(job.progress_pct, 1),
            "log_tail":    list(job.log_tail),
            "error":       job.error,
            "engine":      job.options.engine if job.options else None,
            "started_at":  job.started_at,
            "finished_at": job.finished_at,
            "result_summary": (
                None if job.result is None
                else {
                    "added_tracks":    len(job.result.added_tracks),
                    "added_vias":      len(job.result.added_vias),
                    "elapsed_seconds": job.result.elapsed_seconds,
                    "engine":          job.result.engine,
                }
            ),
        }

    # ---- internal ----------------------------------------------------------
    def _run(self, job: JobState, board: dict) -> None:
        opts = job.options or RouteOptions()
        try:
            engine = get_engine(opts.engine)
        except KeyError as e:
            self._fail(job, str(e))
            return

        with self._lock:
            job.status = "running"
            job.started_at = time.time()

        def on_progress(line: str, pct: float | None) -> None:
            with self._lock:
                if line:
                    job.log_tail.append(line)
                    if len(job.log_tail) > self.LOG_TAIL_MAX:
                        del job.log_tail[: -self.LOG_TAIL_MAX]
                if pct is not None:
                    job.progress_pct = pct

        try:
            result = engine.route(board, opts, on_progress=on_progress)
        except (FreeroutingNotFound, JavaNotFound) as e:
            self._fail(job, f"setup error: {e}")
            return
        except FreeroutingFailed as e:
            self._fail(job, f"freerouting failed: {e}\n{e.stdout}\n{e.stderr}")
            return
        except Exception as e:
            self._fail(job, f"unexpected: {type(e).__name__}: {e}")
            return

        with self._lock:
            job.result = result
            job.status = "done"
            job.finished_at = time.time()
            job.progress_pct = 100.0

    def _fail(self, job: JobState, msg: str) -> None:
        with self._lock:
            job.status = "failed"
            job.error = msg
            job.finished_at = time.time()


# Singleton
manager = JobManager()
