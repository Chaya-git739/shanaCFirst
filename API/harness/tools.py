"""Anthropic API tool schemas, validation, and shared-domain dispatch."""

from __future__ import annotations

import json
from typing import Any

from shared.domain import BridalProfile, ProductCandidate, ShoppingDecision
from shared.search import SearchProvider, search_products
from shared.tools import build_shopping_plan, compare_products


def tool_schemas() -> list[dict[str, Any]]:
    """Return the reduced tool definitions exposed to the API model."""
    return [
        {
            "name": "build_shopping_plan",
            "description": "Build a prioritized bridal shopping checklist from the saved profile.",
            "input_schema": {
                "type": "object",
                "properties": {"as_of": {"type": "string", "format": "date"}},
                "required": [],
                "additionalProperties": False,
            },
        },
        {
            "name": "compare_products",
            "description": "Rank candidate products against budget and style constraints.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "products": {"type": "array", "items": {"type": "object"}},
                    "max_price": {"type": "number", "minimum": 0},
                    "preferred_tags": {"type": "array", "items": {"type": "string"}},
                    "avoid_terms": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["products"],
                "additionalProperties": False,
            },
        },
        {
            "name": "save_decision",
            "description": "Save an explicit preference or decision; conflicting values require confirmation.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "minLength": 1},
                    "value": {},
                    "recorded_at": {"type": "string", "minLength": 10},
                    "source": {"type": "string", "minLength": 1},
                    "confirm_revision": {"type": "boolean"},
                },
                "required": ["key", "value", "recorded_at", "source"],
                "additionalProperties": False,
            },
        },
        {
            "name": "search_products",
            "description": "Search the external product source and return a few unverified listings.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "mark_purchase",
            "description": "Record an item category as purchased or otherwise update its status.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "minLength": 1},
                    "status": {"type": "string", "minLength": 1},
                    "product_id": {"type": "string"},
                },
                "required": ["category", "status"],
                "additionalProperties": False,
            },
        },
        {
            "name": "save_profile",
            "description": "Save profile fields or explicitly confirm revisions to saved values.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "fields": {"type": "object"},
                    "confirm_revision": {"type": "boolean"},
                },
                "required": ["fields"],
                "additionalProperties": False,
            },
        },
    ]


def dispatch_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    profile: BridalProfile,
    memory: Any,
    search_provider: SearchProvider,
) -> dict[str, Any]:
    """Validate and run a tool, returning compact error objects on failure."""
    print(f"[tools.py] dispatch {name}")
    try:
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        if name == "build_shopping_plan":
            _reject_unknown(arguments, {"as_of"})
            saved_profile = memory.profile
            profile = BridalProfile(
                wedding_date=saved_profile.get("wedding_date", profile.wedding_date),
                budget=saved_profile.get("budget", profile.budget),
                currency=saved_profile.get("currency", profile.currency),
                categories=tuple(saved_profile.get("categories", profile.categories)),
                purchased_categories=tuple(saved_profile.get("purchased_categories", profile.purchased_categories)),
                style_preferences=tuple(saved_profile.get("style_preferences", profile.style_preferences)),
                avoid_terms=tuple(saved_profile.get("avoid_terms", profile.avoid_terms)),
            )
            purchased = set(profile.purchased_categories)
            purchased.update(
                category
                for category, record in memory.purchases.items()
                if isinstance(record, dict) and record.get("status") == "purchased"
            )
            current_profile = BridalProfile(
                wedding_date=profile.wedding_date,
                budget=profile.budget,
                currency=profile.currency,
                categories=profile.categories,
                purchased_categories=tuple(sorted(purchased)),
                style_preferences=profile.style_preferences,
                avoid_terms=profile.avoid_terms,
            )
            return build_shopping_plan(current_profile, as_of=arguments.get("as_of"))
        if name == "compare_products":
            _reject_unknown(arguments, {"products", "max_price", "preferred_tags", "avoid_terms", "limit"})
            products = [_product_from_dict(item) for item in arguments["products"]]
            saved_profile = memory.profile
            return compare_products(
                products,
                max_price=arguments.get("max_price", saved_profile.get("budget", profile.budget)),
                preferred_tags=tuple(arguments.get("preferred_tags", saved_profile.get("style_preferences", profile.style_preferences))),
                avoid_terms=tuple(arguments.get("avoid_terms", saved_profile.get("avoid_terms", profile.avoid_terms))),
                limit=arguments.get("limit", 5),
            )
        if name == "save_decision":
            _reject_unknown(arguments, {"key", "value", "recorded_at", "source", "confirm_revision"})
            decision = ShoppingDecision(
                key=arguments["key"],
                value=arguments["value"],
                recorded_at=arguments["recorded_at"],
                source=arguments["source"],
            )
            return memory.save_decision(decision, confirm_revision=arguments.get("confirm_revision", False))
        if name == "mark_purchase":
            _reject_unknown(arguments, {"category", "status", "product_id"})
            memory.save_purchase(arguments["category"], arguments["status"], product_id=arguments.get("product_id"))
            return {"status": "saved", "category": arguments["category"].casefold()}
        if name == "save_profile":
            _reject_unknown(arguments, {"fields", "confirm_revision"})
            result = memory.save_profile(
                arguments["fields"],
                confirm_revision=arguments.get("confirm_revision", False),
            )
            if result["status"] == "conflict" and arguments.get("confirm_revision", False):
                result["status"] = "revised"
            return result
        if name == "search_products":
            _reject_unknown(arguments, {"query", "limit"})
            return search_products(
                search_provider,
                arguments["query"],
                limit=arguments.get("limit", 5),
            )
        raise ValueError(f"unknown tool: {name}")
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(f"[tools.py] tool error {name}")
        return {"is_error": True, "error": str(exc)[:240]}


def tool_result_block(tool_use_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Encode a tool result in Anthropic Messages API format."""
    is_error = bool(result.get("is_error"))
    payload = {key: value for key, value in result.items() if key != "is_error"}
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "is_error": is_error,
    }


def _reject_unknown(arguments: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(arguments).difference(allowed)
    if unknown:
        raise ValueError("unexpected tool argument")


def _product_from_dict(raw: Any) -> ProductCandidate:
    if not isinstance(raw, dict):
        raise ValueError("each product must be an object")
    allowed = {"product_id", "title", "price", "currency", "tags", "url", "source", "verified"}
    _reject_unknown(raw, allowed)
    return ProductCandidate(
        product_id=raw["product_id"],
        title=raw["title"],
        price=raw.get("price"),
        currency=raw.get("currency", "USD"),
        tags=tuple(raw.get("tags", ())),
        url=raw.get("url"),
        source=raw.get("source", "catalog"),
        verified=raw.get("verified", False),
    )
