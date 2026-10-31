"""Evaluate scenario checks against persisted state and recorded tool evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any


def evaluate_checks(
    checks: Sequence[Mapping[str, Any]],
    *,
    profile: Mapping[str, Any],
    decisions: Mapping[str, Any],
    purchases: Mapping[str, Any],
    turns: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return deterministic pass/fail results for persisted-state and tool checks."""
    results: list[dict[str, Any]] = []
    for check in checks:
        check_id = str(check.get("id", "unnamed"))
        kind = check.get("type")
        passed = False
        actual: Any = None
        if kind == "profile_value":
            key = check.get("key")
            actual = profile.get(key)
            passed = actual == check.get("expected")
        elif kind == "profile_field_contains":
            key = check.get("key")
            values = profile.get(key, [])
            actual = check.get("expected_item") in values if isinstance(values, (list, tuple, set)) else False
            passed = bool(actual)
        elif kind == "decision_value":
            key = check.get("key")
            record = decisions.get(key)
            actual = record.get("value") if isinstance(record, Mapping) else getattr(record, "value", None)
            passed = actual == check.get("expected")
        elif kind == "purchased_category":
            category = str(check.get("category", "")).casefold()
            actual = purchases.get(category)
            if not (isinstance(actual, Mapping) and actual.get("status") == "purchased"):
                categories = profile.get("purchased_categories", [])
                actual = category in {str(value).casefold() for value in categories}
                passed = actual
            else:
                passed = True
        elif kind == "tool_used":
            tool_name = check.get("tool")
            actual = [tool.get("name") for turn in turns for tool in turn.get("tools", [])]
            passed = tool_name in actual
        elif kind == "tool_result_contains":
            tool_name = check.get("tool")
            expected_text = str(check.get("expected_text", ""))
            evidence = [
                str(tool.get("preview", ""))
                for turn in turns
                for tool in turn.get("tools", [])
                if tool.get("name") == tool_name
            ]
            actual = {"tool_calls": len(evidence), "matched": any(expected_text in item for item in evidence)}
            passed = bool(evidence) and actual["matched"]
        elif kind == "tool_error_status":
            tool_name = check.get("tool")
            desired_error = bool(check.get("is_error", False))
            actual = [
                tool.get("is_error")
                for turn in turns
                for tool in turn.get("tools", [])
                if tool.get("name") == tool_name
            ]
            passed = bool(actual) and all(value is desired_error for value in actual)
        elif kind == "profile_conflict_observed":
            key = check.get("key")
            expected_value = check.get("proposed_value")
            proposed = expected_value
            actual = False
            for turn in turns:
                for tool in turn.get("tools", []):
                    if tool.get("name") != "save_profile" or tool.get("is_error", False):
                        continue
                    try:
                        payload = json.loads(str(tool.get("preview", "")))
                    except json.JSONDecodeError:
                        continue
                    conflicts = payload.get("conflicts", payload)
                    conflict = conflicts.get(key) if isinstance(conflicts, Mapping) else None
                    if isinstance(conflict, Mapping) and conflict.get("proposed_value") == proposed:
                        actual = True
                        break
                if actual:
                    break
            passed = bool(actual)
        elif kind == "decision_value_not":
            key = check.get("key")
            record = decisions.get(key)
            actual = record.get("value") if isinstance(record, Mapping) else getattr(record, "value", None)
            passed = actual != check.get("not_expected")
        elif kind == "turn_count":
            actual = len(turns)
            passed = actual == check.get("expected")
        elif kind == "no_turn_errors":
            actual = sum(
                1
                for turn in turns
                for tool in turn.get("tools", [])
                if tool.get("is_error")
            )
            failed_turns = sum(1 for turn in turns if turn.get("run_error"))
            actual = {"tool_errors": actual, "run_errors": failed_turns}
            passed = actual["tool_errors"] == 0 and failed_turns == 0
        results.append(
            {
                "id": check_id,
                "passed": passed,
                "actual": actual,
                "expected": check.get("expected", check.get("expected_text")),
                "diagnostic": "passed" if passed else f"check {kind!r} did not match persisted state or run evidence",
            }
        )
    return results


def json_value(value: Any) -> str:
    """Serialize an expected value in the compact format used by tool previews."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
