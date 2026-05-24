"""JSONL trace logging for main and sub agents."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACES_DIR = Path(__file__).resolve().parent.parent / "traces"


class TraceLogger:
    def __init__(self, run_id: str | None = None, agent_id: str = "main") -> None:
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.agent_id = agent_id
        TRACES_DIR.mkdir(parents=True, exist_ok=True)
        self.trace_path = TRACES_DIR / f"{self.run_id}.jsonl"

    def log(self, event_type: str, payload: dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "event_type": event_type,
            "payload": payload,
        }
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")

    def child(self, agent_id: str) -> TraceLogger:
        child = TraceLogger(run_id=self.run_id, agent_id=agent_id)
        return child
