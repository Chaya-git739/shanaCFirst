"""API-harness per-turn context assembly adapter."""

from collections.abc import Mapping, Sequence
from typing import Any

from shared.context import assemble_turn_context, compact_tool_result
from shared.memory import MemoryStore


def build_context(
    message: str,
    memory: MemoryStore,
    *,
    recent_history: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    print("[context.py] selecting relevant turn context")
    return assemble_turn_context(message, memory, recent_history=recent_history)


__all__ = ["build_context", "compact_tool_result"]
