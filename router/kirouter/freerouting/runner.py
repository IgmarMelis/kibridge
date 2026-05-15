"""
Freerouting subprocess runner.

Locates a Freerouting JAR (bundled, or a user-configured path), checks that
Java is installed, runs the JAR headless against a .dsn file, and returns
the resulting .ses file path.

Freerouting CLI is run as:
  java -jar freerouting-x.y.z.jar -de <input.dsn> -do <output.ses> -mp <passes>

Exit code 0 = success. Anything else = look at stdout/stderr for diagnosis.

The user does NOT need to install Java if they don't auto-route; this module
is only invoked when /api/route is hit. The error message tells them where
to download Java if it's missing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable


# Search order for the Freerouting JAR:
#   1. KIROUTER_FREEROUTING_JAR environment variable
#   2. <repo>/router/kirouter/freerouting/bin/freerouting.jar
#   3. ~/.kirouter/freerouting.jar
#
# We do NOT auto-download. The user puts the JAR somewhere we can find,
# or sets the env var. Bundling distributable Java code is a license question
# we keep clean by leaving it to the user (we ship instructions instead).

class FreeroutingNotFound(Exception):
    """Raised when no Freerouting JAR can be located."""


class JavaNotFound(Exception):
    """Raised when 'java' is not on PATH."""


class FreeroutingFailed(Exception):
    """Raised when the subprocess exits non-zero."""
    def __init__(self, code: int, stdout: str, stderr: str):
        super().__init__(f"freerouting exited with code {code}")
        self.code = code
        self.stdout = stdout
        self.stderr = stderr


HERE = Path(__file__).resolve().parent
DEFAULT_JAR_DIRS = [
    HERE / "bin",
    Path.home() / ".kirouter",
]


def find_jar() -> Path:
    env = os.environ.get("KIROUTER_FREEROUTING_JAR")
    if env:
        p = Path(env)
        if p.is_file():
            return p
        raise FreeroutingNotFound(
            f"KIROUTER_FREEROUTING_JAR points to a missing file: {p}")

    for d in DEFAULT_JAR_DIRS:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("freerouting*.jar")):
            return f

    raise FreeroutingNotFound(
        "Freerouting JAR not found. Expected at one of:\n"
        + "\n".join(f"  - {d}" for d in DEFAULT_JAR_DIRS)
        + "\nDownload from: https://github.com/freerouting/freerouting/releases\n"
          "Save freerouting-X.Y.Z.jar into the first directory above, "
          "or set the KIROUTER_FREEROUTING_JAR env var."
    )


def find_java() -> str:
    java = shutil.which("java")
    if java:
        return java
    raise JavaNotFound(
        "'java' was not found on PATH. Install Java 17+ from "
        "https://adoptium.net/temurin/releases/ and re-run."
    )


def check_environment() -> dict:
    """Return a dict describing the runtime — used by /api/route/check."""
    info: dict = {"java": None, "jar": None, "errors": []}
    try:
        info["java"] = find_java()
    except JavaNotFound as e:
        info["errors"].append(str(e))
    try:
        jar = find_jar()
        info["jar"] = str(jar)
        info["jar_size"] = jar.stat().st_size
    except FreeroutingNotFound as e:
        info["errors"].append(str(e))
    info["ok"] = not info["errors"]
    return info


def run_freerouting(
    dsn_path: Path,
    ses_path: Path | None = None,
    *,
    max_passes: int = 30,
    timeout_seconds: float = 600.0,
    on_progress: Callable[[str], None] | None = None,
    java_path: str | None = None,
    jar_path: Path | None = None,
    debug_copy_dir: Path | None = None,
) -> Path:
    """
    Run Freerouting on dsn_path, write to ses_path. Returns ses_path.

    If Freerouting completes successfully but writes no .ses (typically
    because the board has no unrouted nets), creates a minimal empty
    session file so callers don't have to special-case 'nothing to do'.

    If debug_copy_dir is given, the DSN and SES are also copied there
    with timestamps for inspection.

    Raises FreeroutingNotFound, JavaNotFound, FreeroutingFailed.
    """
    java = java_path or find_java()
    jar  = jar_path  or find_jar()

    if ses_path is None:
        ses_path = dsn_path.with_suffix(".ses")

    # CLI args.
    # -Djava.awt.headless=true              : avoid AWT init / GUI warnings
    # -Dfreerouting.analytics.enabled=false : block phone-home (privacy)
    # -de / -do                              : input DSN / output SES
    # -mp                                    : max routing passes
    # The -D...analytics flag is best-effort; older builds may ignore it
    # silently (which is fine — the warning still prints once and never
    # again).
    cmd = [
        java,
        "-Djava.awt.headless=true",
        "-Dfreerouting.analytics.enabled=false",
        "-jar", str(jar),
        "-de", str(dsn_path),
        "-do", str(ses_path),
        "-mp", str(max_passes),
    ]

    if on_progress:
        on_progress(f"$ {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    out_lines: list[str] = []
    started = time.time()

    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        out_lines.append(line)
        if on_progress and line:
            on_progress(line)
        if time.time() - started > timeout_seconds:
            proc.kill()
            raise FreeroutingFailed(
                -1, "\n".join(out_lines),
                f"timed out after {timeout_seconds}s")

    proc.wait()

    # Always copy DSN to debug dir BEFORE we possibly raise — so the user
    # can inspect what was sent even on failure.
    if debug_copy_dir is not None:
        try:
            debug_copy_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            dsn_copy = debug_copy_dir / f"last_{stamp}.dsn"
            dsn_copy.write_bytes(dsn_path.read_bytes())
            if ses_path.is_file():
                ses_copy = debug_copy_dir / f"last_{stamp}.ses"
                ses_copy.write_bytes(ses_path.read_bytes())
        except Exception:
            pass  # debug copy is best-effort

    if proc.returncode != 0:
        raise FreeroutingFailed(
            proc.returncode, "\n".join(out_lines), "")

    # If Freerouting exited cleanly but didn't write a SES (or wrote an
    # empty one), it usually means 'started with 0 unrouted nets' — there
    # was simply nothing to do. We synthesize a valid empty session so
    # the caller can proceed normally; parse_ses will yield 0 tracks/vias.
    if not ses_path.is_file() or ses_path.stat().st_size == 0:
        log_text = "\n".join(out_lines)
        if "0 unrouted nets" in log_text or "started with 0" in log_text:
            ses_path.write_text(
                "(session no_changes\n"
                "  (routes\n"
                "    (resolution um 10)\n"
                "    (parser (host_cad \"freerouting\"))\n"
                "    (network_out))\n"
                ")\n",
                encoding="utf-8",
            )
            if on_progress:
                on_progress(
                    "[KiRouter] Freerouting reported 0 unrouted nets - "
                    "nothing to route. Board returned unchanged."
                )
        else:
            raise FreeroutingFailed(
                0, log_text,
                "Freerouting reported success but produced no .ses file. "
                "This usually means the DSN was malformed - check the "
                "debug copy at " + str(debug_copy_dir) if debug_copy_dir
                else "Freerouting reported success but produced no .ses file."
            )

    return ses_path
