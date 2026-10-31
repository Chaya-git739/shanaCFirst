"""Validated domain records for the bridal-shopping planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


def _require_nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _parse_date(value: str, field_name: str) -> date:
    _require_nonempty(value, field_name)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format") from exc


@dataclass(frozen=True, slots=True)
class BridalProfile:
    """The minimum profile information needed to build a shopping plan."""

    wedding_date: str
    budget: float
    currency: str = "USD"
    categories: tuple[str, ...] = ()
    purchased_categories: tuple[str, ...] = ()
    style_preferences: tuple[str, ...] = ()
    avoid_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _parse_date(self.wedding_date, "wedding_date")
        if isinstance(self.budget, bool) or self.budget < 0:
            raise ValueError("budget must be a non-negative number")
        _require_nonempty(self.currency, "currency")
        for name, values in (
            ("categories", self.categories),
            ("purchased_categories", self.purchased_categories),
            ("style_preferences", self.style_preferences),
            ("avoid_terms", self.avoid_terms),
        ):
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{name} must contain only non-empty strings")


@dataclass(frozen=True, slots=True)
class ShoppingDecision:
    """An explicit saved choice with enough provenance to audit revisions."""

    key: str
    value: Any
    recorded_at: str
    source: str

    def __post_init__(self) -> None:
        _require_nonempty(self.key, "key")
        _require_nonempty(self.source, "source")
        recorded = self.recorded_at
        _require_nonempty(recorded, "recorded_at")
        try:
            date.fromisoformat(recorded.replace("Z", "+00:00").split("T", 1)[0])
        except ValueError as exc:
            raise ValueError("recorded_at must begin with an ISO date") from exc


@dataclass(frozen=True, slots=True)
class ProductCandidate:
    """Normalized product data used for compact comparison results."""

    product_id: str
    title: str
    price: float | None = None
    currency: str = "USD"
    tags: tuple[str, ...] = ()
    url: str | None = None
    source: str = "catalog"
    verified: bool = False

    def __post_init__(self) -> None:
        _require_nonempty(self.product_id, "product_id")
        _require_nonempty(self.title, "title")
        _require_nonempty(self.currency, "currency")
        if self.price is not None and (isinstance(self.price, bool) or self.price < 0):
            raise ValueError("price must be a non-negative number or None")


@dataclass(frozen=True, slots=True)
class ShoppingPlanItem:
    """One concise checklist entry in a bridal shopping plan."""

    category: str
    priority: int
    target_date: str
    estimate_min: float
    estimate_max: float
    reason: str

    def __post_init__(self) -> None:
        _require_nonempty(self.category, "category")
        _parse_date(self.target_date, "target_date")
        _require_nonempty(self.reason, "reason")
        if self.priority < 1:
            raise ValueError("priority must be a positive integer")
        if self.estimate_min < 0 or self.estimate_max < self.estimate_min:
            raise ValueError("estimate range must be non-negative and ordered")


@dataclass(frozen=True, slots=True)
class ProductComparison:
    """Compact comparison result for a single candidate."""

    product_id: str
    score: int
    reasons: tuple[str, ...] = field(default_factory=tuple)
    violations: tuple[str, ...] = field(default_factory=tuple)
