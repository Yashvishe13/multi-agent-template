"""Brief, truncated terminal logging for agent runs."""

from __future__ import annotations

import sys
from datetime import datetime

TRUNCATE = 72


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _trunc(text: str, limit: int = TRUNCATE) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def log(agent: str, message: str) -> None:
    line = f"[{_ts()}] [{agent}] {message}"
    print(line, file=sys.stderr, flush=True)


def main(message: str) -> None:
    log("main", message)


def sub(agent_id: str, subject: str, message: str) -> None:
    label = f"sub:{agent_id[-6:]}"
    log(label, f'"{_trunc(subject, 40)}" {message}')


def run_start(run_id: str, task: str) -> None:
    log("run", f"{run_id} | {_trunc(task)}")
