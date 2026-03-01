from __future__ import annotations

import json
import logging
import signal
from typing import TYPE_CHECKING, Any

from RestrictedPython import PrintCollector, compile_restricted, safe_globals
from RestrictedPython.Eval import default_guarded_getiter
from RestrictedPython.Guards import (
    guarded_unpack_sequence,
    safe_builtins,
    safer_getattr,
)

from app.config import settings

if TYPE_CHECKING:
    from app.core.sessions import Session

logger = logging.getLogger(__name__)

# Exact allowlist of importable modules — no wildcard submodule access.
# Includes pre-injected modules so AI-generated `import pandas as pd` etc.
# are harmless no-ops rather than hard failures.
ALLOWED_IMPORTS = frozenset(
    {
        "math",
        "statistics",
        "json",
        "datetime",
        "collections",
        "pandas",
        "numpy",
        "plotly",
        "plotly.express",
        "plotly.graph_objects",
    }
)


class SandboxTimeoutError(Exception):
    pass


def _timeout_handler(signum: int, frame: Any) -> None:
    raise SandboxTimeoutError("Code execution timed out")


def _restricted_import(
    name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Only allow imports from an explicit allowlist. No submodule wildcards."""
    if name not in ALLOWED_IMPORTS:
        raise ImportError(f"Import of '{name}' is not allowed")
    import builtins

    return builtins.__import__(name, *args, **kwargs)


def _guarded_getitem(obj: Any, key: Any) -> Any:
    """Guard for subscript access (obj[key])."""
    return obj[key]


def _guarded_write(obj: Any) -> Any:
    """Guard for attribute/item assignment. Returns the object as-is."""
    return obj


def _build_globals(session: Session) -> dict[str, Any]:
    import math
    import statistics

    import numpy as np
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go

    restricted_globals = safe_globals.copy()

    # Use safe_builtins as the base — does NOT include getattr,
    # hasattr, type, or other dangerous builtins
    builtins = dict(safe_builtins)
    builtins["__import__"] = _restricted_import
    builtins["print"] = print
    # safe_builtins already has: abs, bool, float, int, isinstance, len,
    # round, sorted, str, tuple, zip. Add the remaining safe builtins
    # that AI-generated data analysis code commonly uses.
    builtins["min"] = min
    builtins["max"] = max
    builtins["sum"] = sum
    builtins["any"] = any
    builtins["all"] = all
    builtins["enumerate"] = enumerate
    builtins["map"] = map
    builtins["filter"] = filter
    builtins["reversed"] = reversed
    builtins["set"] = set
    builtins["frozenset"] = frozenset
    builtins["dict"] = dict
    builtins["list"] = list
    # NOTE: getattr, hasattr, type are intentionally EXCLUDED
    # to prevent sandbox escape via class hierarchy traversal
    restricted_globals["__builtins__"] = builtins

    # RestrictedPython guards
    restricted_globals["_getiter_"] = default_guarded_getiter
    restricted_globals["_getattr_"] = safer_getattr
    restricted_globals["_getitem_"] = _guarded_getitem
    restricted_globals["_write_"] = _guarded_write
    restricted_globals["_unpack_sequence_"] = guarded_unpack_sequence
    restricted_globals["_iter_unpack_sequence_"] = guarded_unpack_sequence
    restricted_globals["_inplacevar_"] = lambda op, x, y: op(x, y)
    restricted_globals["_print_"] = PrintCollector

    # Pre-inject modules — users get these as pre-bound names
    # but cannot traverse their internals via __class__/getattr
    restricted_globals["pd"] = pd
    restricted_globals["np"] = np
    restricted_globals["px"] = px
    restricted_globals["go"] = go
    restricted_globals["math"] = math
    restricted_globals["statistics"] = statistics
    restricted_globals["json"] = json

    # Load dataframes from session tables
    for i, table in enumerate(session.tables):
        try:
            df = session.conn.execute(f"SELECT * FROM {table}").fetchdf()  # noqa: S608
            var_name = "df" if i == 0 else f"df{i + 1}"
            restricted_globals[var_name] = df
            # Also set df0 as alias for df so AI-generated "df0" still works
            if i == 0:
                restricted_globals["df0"] = df
        except Exception:
            pass

    return restricted_globals


def _sanitize_error(error: Exception) -> str:
    """Return a safe error message without leaking internal paths."""
    msg = str(error)
    # Strip file paths
    import re

    msg = re.sub(r"(/[\w./\-]+)+", "<path>", msg)
    # Truncate very long messages
    return msg[:500] if len(msg) > 500 else msg


def execute_code(code: str, session: Session) -> dict[str, Any]:
    # Compile with RestrictedPython
    try:
        byte_code = compile_restricted(code, filename="<sandbox>", mode="exec")
    except SyntaxError as e:
        return {
            "error": f"Syntax error: {e}",
            "stdout": "",
            "figures": [],
            "dataframes": [],
        }

    if byte_code is None:
        return {
            "error": "Code compilation failed",
            "stdout": "",
            "figures": [],
            "dataframes": [],
        }

    sandbox_globals = _build_globals(session)
    sandbox_locals: dict[str, Any] = {}

    # Capture stdout
    captured_output: list[str] = []

    def capturing_print(*args: Any, **kwargs: Any) -> None:
        if len(captured_output) < 200:
            captured_output.append(" ".join(str(a) for a in args))

    sandbox_globals["__builtins__"]["print"] = capturing_print

    # Execute with timeout
    timeout = settings.sandbox_timeout_seconds
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)

    try:
        signal.alarm(timeout)
        exec(byte_code, sandbox_globals, sandbox_locals)  # noqa: S102
        signal.alarm(0)
    except SandboxTimeoutError:
        return {
            "error": f"Execution timed out after {timeout}s",
            "stdout": "\n".join(captured_output),
            "figures": [],
            "dataframes": [],
        }
    except Exception as e:
        signal.alarm(0)
        return {
            "error": _sanitize_error(e),
            "stdout": "\n".join(captured_output),
            "figures": [],
            "dataframes": [],
        }
    finally:
        signal.signal(signal.SIGALRM, old_handler)

    # Extract figures and dataframes from locals
    import pandas as pd
    import plotly.graph_objects as go

    figures = []
    dataframes = []

    for name, val in sandbox_locals.items():
        if name.startswith("_"):
            continue
        if isinstance(val, go.Figure):
            try:
                figures.append(json.loads(val.to_json()))
            except Exception:
                pass
        elif isinstance(val, pd.DataFrame) and name not in (
            "df",
            "df2",
            "df3",
            "df4",
            "df5",
        ):
            try:
                dataframes.append(
                    {
                        "name": name,
                        "data": val.head(100).to_dict(orient="records"),
                        "columns": list(val.columns),
                    }
                )
            except Exception:
                pass

    # Check for a 'fig' variable specifically
    if "fig" in sandbox_locals and isinstance(sandbox_locals["fig"], go.Figure):
        try:
            fig_json = json.loads(sandbox_locals["fig"].to_json())
            if fig_json not in figures:
                figures.insert(0, fig_json)
        except Exception:
            pass

    # Check for a 'result' DataFrame
    if "result" in sandbox_locals and isinstance(sandbox_locals["result"], pd.DataFrame):
        try:
            dataframes.insert(
                0,
                {
                    "name": "result",
                    "data": sandbox_locals["result"].head(100).to_dict(orient="records"),
                    "columns": list(sandbox_locals["result"].columns),
                },
            )
        except Exception:
            pass

    return {
        "error": None,
        "stdout": "\n".join(captured_output),
        "figures": figures,
        "dataframes": dataframes,
    }
