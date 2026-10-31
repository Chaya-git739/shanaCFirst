"""Deterministic conversation compaction without replacing structured memory."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _log(action: str) -> None:
    print(f"[compaction.py] {action}")


def compact_history(
    history: Sequence[Mapping[str, Any]],
    *,
    max_messages: int = 12,
    keep_recent: int = 4,
    max_summary_chars: int = 1600,
) -> dict[str, Any]:
    """Return a compact summary and recent messages when history exceeds threshold.

    This is deliberately extractive: it retains short message text rather than
    making model calls or inventing summarized facts. Structured decisions and
    constraints must be read from persistent memory, not reconstructed here.
    """
    if max_messages < 1 or keep_recent < 0 or max_summary_chars < 1:
        raise ValueError("compaction limits must be positive (keep_recent may be zero)")
    normalized = [
        {"role": str(message.get("role", "")), "content": str(message.get("content", ""))}
        for message in history
        if message.get("role") and message.get("content")
    ]
    if len(normalized) <= max_messages:
        _log("history below compaction threshold")
        return {"compacted": False, "summary": "", "recent_history": normalized}

    recent = normalized[-keep_recent:] if keep_recent else []
    older = normalized[:-keep_recent] if keep_recent else normalized
    summary = _extract_summary(older, max_summary_chars)
    _log(f"compacted history ({len(older)} older messages summarized)")
    return {"compacted": True, "summary": summary, "recent_history": recent}


def _extract_summary(messages: Sequence[Mapping[str, str]], max_chars: int) -> str:
    """Keep bounded, labeled snippets of older turns for conversational continuity."""
    snippets: list[str] = []
    remaining = max_chars
    for message in messages:
        content = " ".join(str(message["content"]).split())
        if not content or remaining <= 0:
            continue
        role = message["role"][:16]
        prefix = f"{role}: "
        available = max(0, remaining - len(prefix))
        snippet = content[:available]
        if not snippet:
            break
        formatted = prefix + snippet
        snippets.append(formatted)
        remaining -= len(formatted) + 1
    return "\n".join(snippets)
