"""Anthropic prompt cache boundary helpers."""

from __future__ import annotations

from typing import Any


def cache_system_prompt(text: str, *, enabled: bool = True) -> list[dict[str, Any]] | str:
    """Return a cacheable system block when enabled, plain text otherwise."""
    if not enabled:
        print("[caching.py] prompt caching disabled")
        return text
    print("[caching.py] configured system prompt cache boundary")
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def cache_tool_definitions(tools: list[dict[str, Any]], *, enabled: bool = True) -> list[dict[str, Any]]:
    """Copy tools and mark the final definition as a cache boundary."""
    copied = [dict(tool) for tool in tools]
    if enabled and copied:
        copied[-1]["cache_control"] = {"type": "ephemeral"}
        print("[caching.py] configured tool cache boundary")
    return copied
