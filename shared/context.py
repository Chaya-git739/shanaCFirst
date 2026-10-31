"""Per-turn context selection and compact, safe conversation-history handling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from shared.memory import MemoryStore


_DEFAULT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "budget": ("budget", "cost", "price", "afford", "spend", "remaining"),
    "plan": ("plan", "checklist", "prioritize", "schedule", "remaining"),
    "product": ("product", "shoe", "dress", "accessory", "search", "option"),
    "decision": ("decision", "choose", "chosen", "reject", "saved", "remember"),
    "purchase": ("bought", "purchased", "purchase", "already have"),
    "style": ("style", "color", "fabric", "ivory", "silhouette", "preference"),
}


def _log(action: str) -> None:
    print(f"[context.py] {action}")


def classify_turn(message: str) -> set[str]:
    """Infer small, explainable topic tags from the current user request."""
    lowered = message.casefold()
    return {
        topic
        for topic, keywords in _DEFAULT_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    }


def assemble_turn_context(
    message: str,
    memory: MemoryStore,
    *,
    recent_history: Sequence[Mapping[str, Any]] = (),
    history_limit: int = 2,
    memory_limit: int = 8,
) -> dict[str, Any]:
    """Build a small context payload from the current request and relevant memory.

    History entries are expected to contain ``role`` and ``content`` fields;
    only the last ``history_limit`` entries are retained. The full transcript and
    unrelated memory are never included.
    """
    if history_limit < 0 or memory_limit < 1:
        raise ValueError("history_limit must be non-negative and memory_limit positive")
    topics = classify_turn(message)
    # Include the user's own terms as well as coarse tags so key-specific
    # memory (for example ``selected_shoes``) can be retrieved on recall turns.
    query = " ".join((*sorted(topics), message))
    relevant_memory = memory.get_relevant_context(query, limit=memory_limit)
    history = [
        {"role": str(item.get("role", "")), "content": str(item.get("content", ""))[:1200]}
        for item in recent_history[-history_limit:]
        if item.get("role") and item.get("content")
    ] if history_limit else []
    result = {
        "user_message": message,
        "topics": sorted(topics),
        "memory": relevant_memory,
        "recent_history": history,
        "included_sources": ["current_message"]
        + (["relevant_memory"] if any(relevant_memory.values()) else [])
        + (["recent_history"] if history else []),
    }
    _log(f"assembled turn context ({len(result['included_sources'])} sources)")
    return result


def compact_tool_result(value: Any, *, max_chars: int = 3000, max_items: int = 10) -> Any:
    """Bound tool-result size and item counts while preserving JSON-like structure."""
    if max_chars < 1 or max_items < 1:
        raise ValueError("max_chars and max_items must be positive")
    compacted = _compact_value(value, max_items=max_items, max_string=max_chars)
    encoded_size = len(str(compacted))
    if encoded_size <= max_chars:
        return compacted
    if isinstance(compacted, dict):
        return {"status": compacted.get("status", "truncated"), "truncated": True}
    return {"status": "truncated", "truncated": True}


def _compact_value(value: Any, *, max_items: int, max_string: int) -> Any:
    if isinstance(value, str):
        return value[:max_string]
    if isinstance(value, Mapping):
        return {
            str(key)[:80]: _compact_value(item, max_items=max_items, max_string=max_string)
            for key, item in list(value.items())[:max_items]
        }
    if isinstance(value, (list, tuple)):
        return [_compact_value(item, max_items=max_items, max_string=max_string) for item in value[:max_items]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:max_string]
