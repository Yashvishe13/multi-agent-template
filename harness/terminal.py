"""Subprocess terminal execution for agent code actions."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CWD = Path.cwd()
DEFAULT_TIMEOUT = 120


@dataclass
class TerminalResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    success: bool


def run_command(command: str, cwd: Path | None = None, timeout: int = DEFAULT_TIMEOUT) -> TerminalResult:
    workdir = cwd or DEFAULT_CWD
    completed = subprocess.run(
        command,
        shell=True,
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return TerminalResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        success=completed.returncode == 0,
    )
