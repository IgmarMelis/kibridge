"""
script_runner - validate and execute scripts written by Copilot.

Two-phase defense:
  1. Static AST analysis - rejects forbidden imports, dunders, eval/exec,
     open(), and any attempt to escape the sandbox.
  2. Restricted exec() - scripts run with a curated __builtins__ dict and
     ONLY kibridge_api visible as a module. They cannot import anything else.

This is "good enough" against Copilot mistakes. It is NOT a security
boundary against an adversarial attacker. The threat model is:
"Copilot proposes wrong code", not "Copilot is malicious".
"""
from __future__ import annotations

import ast

ALLOWED_IMPORTS = {"kibridge_api"}

FORBIDDEN_BUILTINS = {
    "eval", "exec", "compile", "open", "__import__",
    "input", "breakpoint", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "hasattr",
}

SAFE_BUILTINS = {
    "len": len, "range": range, "list": list, "dict": dict, "tuple": tuple,
    "set": set, "frozenset": frozenset, "str": str, "int": int, "float": float,
    "bool": bool, "True": True, "False": False, "None": None,
    "print": print, "isinstance": isinstance, "issubclass": issubclass,
    "abs": abs, "min": min, "max": max, "round": round, "sum": sum,
    "sorted": sorted, "reversed": reversed,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "any": any, "all": all,
    "ValueError": ValueError, "TypeError": TypeError, "KeyError": KeyError,
    "IndexError": IndexError, "RuntimeError": RuntimeError,
    "Exception": Exception,
}


class ScriptValidationError(Exception):
    """Raised when a script fails AST validation."""


def validate_script(source: str, filename: str = "<script>") -> None:
    """Parse and statically check a script. Raises ScriptValidationError on any violation."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        raise ScriptValidationError(f"{filename}: syntax error: {e}") from e

    for node in ast.walk(tree):
        # Block import of anything except kibridge_api
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    raise ScriptValidationError(
                        f"{filename}:{node.lineno}: forbidden import '{alias.name}'. "
                        f"Only allowed: {sorted(ALLOWED_IMPORTS)}"
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod not in ALLOWED_IMPORTS:
                raise ScriptValidationError(
                    f"{filename}:{node.lineno}: forbidden 'from {node.module} import ...'"
                )

        # Block dunder access (escape vector for sandboxes)
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise ScriptValidationError(
                    f"{filename}:{node.lineno}: forbidden dunder attribute "
                    f"'{node.attr}'"
                )

        # Block forbidden builtins by name
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_BUILTINS:
            raise ScriptValidationError(
                f"{filename}:{node.lineno}: forbidden builtin '{node.id}'"
            )

        # Block dynamic exec/eval calls
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_BUILTINS:
                raise ScriptValidationError(
                    f"{filename}:{node.lineno}: forbidden call '{node.func.id}'"
                )


def _make_safe_import(kibridge_api_module):
    """
    Return a controlled __import__ that resolves ONLY whitelisted modules.
    The AST validator already blocks 'import os' etc. at parse time, but
    Python's import statement still needs __import__ at runtime to resolve
    even legitimate 'import kibridge_api' calls. This function gives it exactly
    that, and nothing more.
    """
    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if root not in ALLOWED_IMPORTS:
            raise ImportError(
                f"forbidden import '{name}' at runtime "
                f"(only {sorted(ALLOWED_IMPORTS)} allowed)"
            )
        if root == "kibridge_api":
            return kibridge_api_module
        raise ImportError(f"unknown allowed module '{name}'")
    return _safe_import


def run_script(source: str, kibridge_api_module, board, dry_run: bool,
               filename: str = "<script>"):
    """
    Validate and run a script. Returns the script's local kibridge_api log
    (the list of recorded ops).

    Raises ScriptValidationError on validation failure (script never executes).
    Other exceptions during execution are wrapped and re-raised.
    """
    validate_script(source, filename=filename)

    # Inject the active board and dry_run flag into kibridge_api,
    # then reset the per-run log.
    kibridge_api_module._board = board
    kibridge_api_module._dry_run = bool(dry_run)
    kibridge_api_module._log = []

    builtins_dict = dict(SAFE_BUILTINS)
    builtins_dict["__import__"] = _make_safe_import(kibridge_api_module)

    safe_globals = {
        "__builtins__": builtins_dict,
        "kibridge_api": kibridge_api_module,
    }

    try:
        compiled = compile(source, filename, "exec")
        exec(compiled, safe_globals)  # noqa: S102
    except ScriptValidationError:
        raise
    except Exception as e:
        raise RuntimeError(f"{filename}: runtime error: {e}") from e

    # Snapshot the log and detach the board reference.
    log = list(kibridge_api_module._log)
    kibridge_api_module._board = None
    kibridge_api_module._log = []
    return log
