"""Deterministic, compact shared bridal-shopping tools."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from shared.domain import (
    BridalProfile,
    ProductCandidate,
    ProductComparison,
    ShoppingDecision,
    ShoppingPlanItem,
)


# Planning lead times and broad estimates are guidance, not live price quotes.
_CATEGORY_GUIDANCE: dict[str, tuple[int, float, float, str]] = {
    "dress": (180, 600.0, 2500.0, "Allow time for ordering and multiple fittings."),
    "alterations": (45, 100.0, 600.0, "Schedule fittings before the wedding date."),
    "shoes": (90, 80.0, 300.0, "Leave time to break in and test the shoes."),
    "accessories": (60, 50.0, 400.0, "Coordinate accessories after the outfit is selected."),
    "getting_ready": (30, 30.0, 200.0, "Choose this after confirming the getting-ready schedule."),
    "beauty": (30, 100.0, 500.0, "Book trials and appointments ahead of the event."),
    "emergency_kit": (7, 20.0, 80.0, "Assemble close to the wedding once plans are final."),
}


def _log(action: str) -> None:
    print(f"[tools.py] {action}")


def build_shopping_plan(
    profile: BridalProfile,
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Build a prioritized plan while omitting already-purchased categories."""
    _log("build_shopping_plan")
    wedding = date.fromisoformat(profile.wedding_date)
    today = date.fromisoformat(as_of) if as_of else date.today()
    purchased = {category.casefold() for category in profile.purchased_categories}
    requested = profile.categories or tuple(_CATEGORY_GUIDANCE)
    categories = list(dict.fromkeys(category.casefold() for category in requested))

    items: list[ShoppingPlanItem] = []
    for category in categories:
        if category in purchased or category not in _CATEGORY_GUIDANCE:
            continue
        lead_days, estimate_min, estimate_max, reason = _CATEGORY_GUIDANCE[category]
        target = wedding - timedelta(days=lead_days)
        days_until_target = (target - today).days
        priority = 1 if days_until_target <= 14 else 2 if days_until_target <= 60 else 3
        items.append(
            ShoppingPlanItem(
                category=category,
                priority=priority,
                target_date=max(target, today).isoformat(),
                estimate_min=estimate_min,
                estimate_max=estimate_max,
                reason=reason,
            )
        )

    items.sort(key=lambda item: (item.target_date, item.category))
    estimate_min = round(sum(item.estimate_min for item in items), 2)
    estimate_max = round(sum(item.estimate_max for item in items), 2)
    return {
        "items": [
            {
                "category": item.category,
                "priority": item.priority,
                "target_date": item.target_date,
                "estimate": {"min": item.estimate_min, "max": item.estimate_max, "currency": profile.currency},
                "reason": item.reason,
            }
            for item in items
        ],
        "estimate_total": {"min": estimate_min, "max": estimate_max, "currency": profile.currency},
        "budget": {"amount": profile.budget, "currency": profile.currency},
        "budget_note": "Estimate is a planning range; compare it with the budget before committing.",
    }


def compare_products(
    products: list[ProductCandidate],
    *,
    max_price: float | None = None,
    preferred_tags: tuple[str, ...] = (),
    avoid_terms: tuple[str, ...] = (),
    limit: int = 5,
) -> dict[str, Any]:
    """Rank candidates against budget and explicitly supplied style constraints."""
    _log("compare_products")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if max_price is not None and max_price < 0:
        raise ValueError("max_price must be non-negative")

    preferred = {tag.casefold() for tag in preferred_tags}
    avoided = {term.casefold() for term in avoid_terms}
    scored: list[ProductComparison] = []
    for product in products:
        tags = {tag.casefold() for tag in product.tags}
        searchable = f"{product.title} {' '.join(product.tags)}".casefold()
        reasons: list[str] = []
        violations: list[str] = []
        score = 0
        if max_price is not None:
            if product.price is None:
                violations.append("price_unknown")
            elif product.price > max_price:
                violations.append("over_budget")
            else:
                score += 2
                reasons.append("within_budget")
        matched = preferred.intersection(tags)
        if matched:
            score += len(matched)
            reasons.append("matches_preferences:" + ",".join(sorted(matched)))
        found_avoid = sorted(term for term in avoided if term in searchable)
        if found_avoid:
            violations.append("avoid_terms:" + ",".join(found_avoid))
            score -= len(found_avoid) * 3
        scored.append(ProductComparison(product.product_id, score, tuple(reasons), tuple(violations)))

    scored.sort(key=lambda result: (-result.score, bool(result.violations), result.product_id))
    return {
        "results": [
            {
                "product_id": result.product_id,
                "score": result.score,
                "reasons": list(result.reasons),
                "violations": list(result.violations),
            }
            for result in scored[:limit]
        ]
    }


def save_decision(
    decisions: dict[str, ShoppingDecision],
    decision: ShoppingDecision,
    *,
    confirm_revision: bool = False,
) -> dict[str, Any]:
    """Save an explicit decision; conflicting values require confirmed revision."""
    _log("save_decision")
    existing = decisions.get(decision.key)
    if existing is None:
        decisions[decision.key] = decision
        return {"status": "saved", "key": decision.key}
    if existing.value == decision.value:
        return {"status": "unchanged", "key": decision.key}
    if not confirm_revision:
        return {
            "status": "conflict",
            "key": decision.key,
            "saved_value": existing.value,
            "proposed_value": decision.value,
            "requires_confirmation": True,
        }
    decisions[decision.key] = decision
    return {"status": "revised", "key": decision.key}
