"""API-harness history compaction adapter."""

from collections.abc import Mapping, Sequence
from typing import Any

from shared.compaction import compact_history


def compact_if_needed(history: Sequence[Mapping[str, Any]], *, threshold: int = 12) -> dict[str, Any]:
    print("[compaction.py] checking history threshold")
    return compact_history(history, max_messages=threshold)
