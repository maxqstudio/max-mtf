from __future__ import annotations

import os
from collections.abc import Mapping

ACCEPTANCE_UTF8_MARKER = "MAX_MTF_ACCEPTANCE_UTF8"
PYTHON_UTF8_ENV = "PYTHONUTF8"
PYTHON_IO_ENCODING_ENV = "PYTHONIOENCODING"


def acceptance_utf8_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an acceptance-process environment with deterministic UTF-8 Python text I/O.

    Canonical acceptance frequently redirects/captures stdout.  On Windows, redirected
    child Python processes can otherwise fall back to a legacy code page such as CP1252
    and fail while printing valid UTF-8 source/test messages.  Keep this scoped to
    acceptance execution rather than changing normal application runtime globally.
    """
    env = dict(os.environ if base is None else base)
    env[PYTHON_UTF8_ENV] = "1"
    env[PYTHON_IO_ENCODING_ENV] = "utf-8"
    env[ACCEPTANCE_UTF8_MARKER] = "1"
    return env


def utf8_text_subprocess_kwargs() -> dict[str, str]:
    """Deterministic parent-side decoding for captured Python acceptance output."""
    return {"encoding": "utf-8", "errors": "replace"}
