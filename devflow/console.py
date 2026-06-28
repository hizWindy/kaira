"""Shared Rich console instance configured for Windows UTF-8 compatibility."""

from __future__ import annotations

import os
import sys

# Ensure stdout/stderr use UTF-8 on Windows before Rich initialises.
# This handles the legacy cp1252 Windows console that can't render ✓ ⚠ etc.
if sys.platform == "win32":
    # Reconfigure stdout/stderr to use UTF-8 if supported (Python 3.7+).
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from rich.console import Console  # noqa: E402 — must come after reconfigure

console = Console(legacy_windows=False, safe_box=True)
err_console = Console(legacy_windows=False, safe_box=True, stderr=True)
