"""Explicit Messages API model/tool loop with batched tool results."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from API.harness.tokens import TurnMetrics, add_usage
from API.harness.tools import dispatch_tool, tool_result_block
from API.agent import request_options
from shared.context import compact_tool_result
from shared.domain import BridalProfile
from shared.search import SearchProvider


class ModelProtocolError(RuntimeError):
    """Raised when the model client returns an invalid response shape."""


def run_turn(
    client: Any,
    *,
    model: str,
    system: Any,
    messages: list[dict[str, Any]],
    profile: BridalProfile,
    memory: Any,
    search_provider: SearchProvider,
    metrics: TurnMetrics,
    max_tool_rounds: int = 8,
    on_message: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run until the assistant stops or reaches the safe tool-round limit."""
    if max_tool_rounds < 1:
        raise ValueError("max_tool_rounds must be at least one")
    working_messages = list(messages)
    final_response: Any = None

    for _round in range(max_tool_rounds + 1):
        print(f"[loop.py] model call {metrics.model_calls + 1}")
        started = time.perf_counter()
        response = client.messages.create(
            **{**request_options(), "model": model},
            system=system,
            tools=_tools_with_cached_boundary(),
            messages=working_messages,
        )
        metrics.model_calls += 1
        metrics.elapsed_ms += (time.perf_counter() - started) * 1000
        add_usage(metrics, _value(response, "usage", {}))
        response_dict = _as_dict(response)
        content = response_dict.get("content", [])
        if not isinstance(content, list):
            raise ModelProtocolError("model content must be a list")
        if on_message:
            on_message({"role": "assistant", "content": content})

        if response_dict.get("stop_reason") != "tool_use":
            final_response = response
            break
        if _round >= max_tool_rounds:
            raise ModelProtocolError("maximum tool rounds exceeded")

        tool_blocks = [block for block in content if _value(block, "type") == "tool_use"]
        if not tool_blocks:
            raise ModelProtocolError("stop_reason requested tool use without tool_use blocks")
        working_messages.append({"role": "assistant", "content": content})
        tool_results: list[dict[str, Any]] = []
        for block in tool_blocks:
            name = _value(block, "name")
            tool_id = _value(block, "id")
            raw_input = _value(block, "input", {})
            if not isinstance(name, str) or not isinstance(tool_id, str) or not isinstance(raw_input, dict):
                result = {"is_error": True, "error": "invalid tool-use block"}
                tool_name = str(name or "unknown")
            else:
                tool_name = name
                result = dispatch_tool(
                    name,
                    raw_input,
                    profile=profile,
                    memory=memory,
                    search_provider=search_provider,
                )
            compacted = compact_tool_result(result, max_chars=3000, max_items=10)
            metrics.tools.append(
                {
                    "name": tool_name,
                    "is_error": bool(result.get("is_error", False)),
                    "preview": json.dumps(compacted, ensure_ascii=False, separators=(",", ":"))[:600],
                }
            )
            tool_results.append(tool_result_block(str(tool_id or "invalid"), compacted))
        working_messages.append({"role": "user", "content": tool_results})
        if on_message:
            on_message(working_messages[-1])
    else:
        raise ModelProtocolError("model loop terminated unexpectedly")

    return {
        "response": final_response,
        "messages": working_messages,
        "metrics": metrics.to_dict(),
    }


def _tools_with_cached_boundary() -> list[dict[str, Any]]:
    from API.harness.caching import cache_tool_definitions
    from API.harness.tools import tool_schemas

    return cache_tool_definitions(tool_schemas())


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _as_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, Mapping):
        return dict(response)
    if hasattr(response, "model_dump"):
        return response.model_dump()
    return {
        "content": _value(response, "content", []),
        "stop_reason": _value(response, "stop_reason"),
    }
