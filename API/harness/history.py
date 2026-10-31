"""Append-only JSONL conversation history with session filtering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_message(path: str | Path, session_id: str, message: dict[str, Any]) -> None:
    if not session_id.strip():
        raise ValueError("session_id must not be empty")
    record = {"session_id": session_id, "message": message}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    print("[history.py] appended message")


def load_session(path: str | Path, session_id: str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    messages: list[dict[str, Any]] = []
    with target.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("session_id") == session_id and isinstance(record.get("message"), dict):
                messages.append(record["message"])
    print(f"[history.py] loaded {len(messages)} messages")
    return messages
