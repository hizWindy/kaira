"""Execute Python snippets inside the generated project's interpreter.

Provisioning, seeding, and clearing all need to import the *project's* modules
(``core.database``, ``models.*``) using the project's virtualenv — not Kaira's.
Centralising that here keeps the PYTHONPATH and interpreter resolution in one
place instead of repeated at every call site.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _project_env(output_root: Path) -> dict[str, str]:
    """Build the subprocess environment for running project code."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(output_root) + os.pathsep + env.get("PYTHONPATH", "")
    # Generated scripts print status with em dashes and emoji; Windows consoles
    # default to cp1252 and would raise UnicodeEncodeError mid-run.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _run(argv: list[str], output_root: Path, capture: bool) -> subprocess.CompletedProcess:
    from kaira.config import get_venv_python

    return subprocess.run(
        [get_venv_python(), *argv],
        cwd=str(output_root),
        env=_project_env(output_root),
        text=True,
        capture_output=capture,
    )


def run_project_script(
    code: str,
    output_root: Path,
    *,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run ``code`` in the generated project's Python interpreter.

    Args:
        code: Python source to execute via ``python -c``.
        output_root: Project root, prepended to PYTHONPATH so ``core`` and
            ``models`` are importable.
        capture: Capture stdout/stderr instead of streaming to the terminal.

    Returns:
        The completed process. The caller inspects ``returncode`` — this does
        not raise on a non-zero exit, so failures can be reported with their
        captured output rather than a bare CalledProcessError.
    """
    return _run(["-c", code], output_root, capture)


def run_project_file(
    script: Path,
    output_root: Path,
    *,
    args: list[str] | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a script file in the generated project's Python interpreter.

    Args:
        script: Path to the script to execute.
        output_root: Project root, prepended to PYTHONPATH.
        args: Additional command-line arguments passed to the script.
        capture: Capture stdout/stderr instead of streaming to the terminal.

    Returns:
        The completed process; does not raise on a non-zero exit.
    """
    return _run([str(script), *(args or [])], output_root, capture)
