"""Per-turn token, cost, and elapsed-time metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TurnMetrics:
    session_id: str
    turn: int
    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    tools: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float | None = None
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn": self.turn,
            "tokens": {
                "input": self.input_tokens,
                "cache_read": self.cache_read_tokens,
                "cache_write": self.cache_write_tokens,
                "output": self.output_tokens,
            },
            "model_calls": self.model_calls,
            "tools": self.tools,
            "cost_usd": self.cost_usd,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


def add_usage(metrics: TurnMetrics, usage: Any) -> None:
    """Accumulate usage fields across model calls, tolerating optional fields."""
    metrics.input_tokens += int(_get(usage, "input_tokens", 0) or 0)
    metrics.output_tokens += int(_get(usage, "output_tokens", 0) or 0)
    metrics.cache_read_tokens += int(_get(usage, "cache_read_input_tokens", 0) or 0)
    metrics.cache_write_tokens += int(_get(usage, "cache_creation_input_tokens", 0) or 0)
    cost = _get(usage, "cost_usd", None)
    if cost is not None:
        metrics.cost_usd = (metrics.cost_usd or 0.0) + float(cost)


def _get(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)
