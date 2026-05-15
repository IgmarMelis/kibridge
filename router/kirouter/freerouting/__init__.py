"""
freerouting/ — Specctra DSN/SES IO + headless JAR runner.

This subpackage owns everything Freerouting-specific. The router engine
calls into it through a stable interface so we can later add other
routing backends without touching the rest of KiRouter.
"""
from .dsn_export import export_dsn
from .ses_import import parse_ses, parse_sexpr
from .runner import (
    check_environment,
    find_java,
    find_jar,
    run_freerouting,
    FreeroutingNotFound,
    JavaNotFound,
    FreeroutingFailed,
)

__all__ = [
    "export_dsn",
    "parse_ses",
    "parse_sexpr",
    "check_environment",
    "find_java",
    "find_jar",
    "run_freerouting",
    "FreeroutingNotFound",
    "JavaNotFound",
    "FreeroutingFailed",
]
