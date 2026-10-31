"""External product-search boundary with compact response normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class SearchProvider(Protocol):
    """Adapter contract for an external product search provider."""

    def search(self, query: str, limit: int, timeout_seconds: float) -> list[dict[str, Any]]:
        """Return raw provider records; implementations should enforce timeout."""
        ...


@dataclass(slots=True)
class MockSearchProvider:
    """Deterministic offline provider used by tests and demonstrations."""

    records: list[dict[str, Any]]
    error: str | None = None

    def search(self, query: str, limit: int, timeout_seconds: float) -> list[dict[str, Any]]:
        if self.error:
            raise RuntimeError(self.error)
        query_terms = {term.casefold() for term in query.split() if len(term) > 2}
        matches = [
            record
            for record in self.records
            if not query_terms
            or query_terms.intersection(
                set(str(record.get("title", "")).casefold().split())
                | set(str(record.get("excerpt", "")).casefold().split())
            )
        ]
        return matches[:limit]


def search_products(
    provider: SearchProvider,
    query: str,
    *,
    limit: int = 5,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Call an injected provider and return bounded, normalized, untrusted results."""
    print("[search.py] search_products")
    if not query.strip():
        raise ValueError("query must not be empty")
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    try:
        raw_results = provider.search(query, limit, timeout_seconds)
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__, "results": []}

    normalized: list[dict[str, Any]] = []
    for raw in raw_results[:limit]:
        title = str(raw.get("title", "")).strip()
        url = str(raw.get("url", "")).strip()
        if not title or not url:
            continue
        price = raw.get("price")
        normalized.append(
            {
                "title": title[:120],
                "url": url[:500],
                "price": price if isinstance(price, (int, float)) and not isinstance(price, bool) else None,
                "currency": str(raw.get("currency", "USD"))[:8],
                "seller": str(raw.get("seller", ""))[:80] or None,
                "checked_at": str(raw.get("checked_at", ""))[:40] or None,
                "excerpt": str(raw.get("excerpt", ""))[:240],
                "source": "external_unverified",
            }
        )
    return {"status": "ok", "results": normalized}
