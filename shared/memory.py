"""Small JSON-backed, explicit memory store for cross-session agent state."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from shared.domain import ShoppingDecision
from shared.tools import save_decision as resolve_decision

_SCHEMA_VERSION = 1


def _log(action: str) -> None:
    print(f"[memory.py] {action}")


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "profile": {},
        "decisions": {},
        "purchases": {},
        "sessions": [],
    }


class MemoryStore:
    """Persist profile facts and decisions in a caller-selected state file.

    This class does not choose a default storage location. Callers should pass a
    dedicated per-user/per-run path and avoid placing credentials in stored data.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            _log("initialized empty state")
            return _empty_state()
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not load memory state: {self.path}") from exc
        if not isinstance(state, dict) or state.get("schema_version") != _SCHEMA_VERSION:
            raise ValueError("Unsupported or invalid memory schema")
        for field in ("profile", "decisions", "purchases", "sessions"):
            if field not in state:
                raise ValueError(f"Memory state is missing {field!r}")
        if not all(isinstance(state[field], dict) for field in ("profile", "decisions", "purchases")):
            raise ValueError("Memory profile, decisions, and purchases must be objects")
        if not isinstance(state["sessions"], list):
            raise ValueError("Memory sessions must be a list")
        _log("loaded state")
        return state

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._state, ensure_ascii=False, separators=(",", ":"))
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as temporary_file:
                temporary_path = temporary_file.name
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @property
    def profile(self) -> dict[str, Any]:
        """Return a defensive copy of explicitly saved profile facts."""
        return dict(self._state["profile"])

    @property
    def decisions(self) -> dict[str, ShoppingDecision]:
        """Return saved decisions as validated domain records."""
        return {
            key: ShoppingDecision(**record)
            for key, record in self._state["decisions"].items()
        }

    @property
    def purchases(self) -> dict[str, Any]:
        """Return a defensive copy of purchase status."""
        return dict(self._state["purchases"])

    def save_profile(
        self,
        fields: dict[str, Any],
        *,
        confirm_revision: bool = False,
    ) -> dict[str, Any]:
        """Save profile facts; conflicting values require explicit confirmation."""
        json.dumps(fields)
        conflicts = {
            key: {"saved_value": self._state["profile"][key], "proposed_value": value}
            for key, value in fields.items()
            if key in self._state["profile"] and self._state["profile"][key] != value
        }
        if conflicts:
            if confirm_revision:
                self._state["profile"].update(fields)
                self._persist()
                _log(f"confirmed profile revision ({len(conflicts)} fields)")
                return {"status": "revised", "field_count": len(fields)}
            _log(f"profile update conflict ({len(conflicts)} fields)")
            return {"status": "conflict", "conflicts": conflicts, "requires_confirmation": True}
        self._state["profile"].update(fields)
        self._persist()
        _log(f"saved profile fields ({len(fields)})")
        return {"status": "saved", "field_count": len(fields)}

    def save_decision(
        self,
        decision: ShoppingDecision,
        *,
        confirm_revision: bool = False,
    ) -> dict[str, Any]:
        """Persist an explicit decision, preserving conflicts unless confirmed."""
        records = self._state["decisions"]
        existing = records.get(decision.key)
        current = ShoppingDecision(**existing) if existing else None
        decisions = {decision.key: current} if current else {}
        result = resolve_decision(decisions, decision, confirm_revision=confirm_revision)
        if result["status"] in {"saved", "revised"}:
            records[decision.key] = {
                "key": decision.key,
                "value": decision.value,
                "recorded_at": decision.recorded_at,
                "source": decision.source,
            }
            self._persist()
        _log(f"decision {result['status']}")
        return result

    def save_purchase(self, category: str, status: str, *, product_id: str | None = None) -> None:
        """Record concise purchase status for a category."""
        if not category.strip() or not status.strip():
            raise ValueError("category and status must be non-empty")
        record: dict[str, Any] = {"status": status}
        if product_id is not None:
            record["product_id"] = product_id
        self._state["purchases"][category.casefold()] = record
        self._persist()
        _log("saved purchase status")

    def get_purchase_status(self, category: str) -> dict[str, Any] | None:
        """Return purchase status for one category without exposing unrelated state."""
        if not category.strip():
            raise ValueError("category must be non-empty")
        return dict(self._state["purchases"].get(category.casefold(), {})) or None

    def record_session(self, session_id: str) -> None:
        """Append a session ID once, without storing credentials or messages."""
        if not session_id.strip():
            raise ValueError("session_id must be non-empty")
        if session_id not in self._state["sessions"]:
            self._state["sessions"].append(session_id)
            self._persist()
            _log("recorded session")

    def get_relevant_context(self, topic: str, *, limit: int = 8) -> dict[str, Any]:
        """Retrieve only saved profile, decision, and purchase entries relevant to a topic."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        terms = {term.casefold() for term in topic.replace("_", " ").split() if term}

        def relevant(key: str) -> bool:
            normalized = key.casefold().replace("_", " ")
            key_terms = set(normalized.split())
            return not terms or bool(terms.intersection(key_terms)) or any(
                len(term) >= 4 and term in normalized for term in terms
            )

        profile = {key: value for key, value in self._state["profile"].items() if relevant(key)}
        decisions = {
            key: record
            for key, record in self._state["decisions"].items()
            if relevant(key)
        }
        purchases = {
            key: value for key, value in self._state["purchases"].items() if relevant(key)
        }
        result = {
            "profile": dict(list(profile.items())[:limit]),
            "decisions": dict(list(decisions.items())[:limit]),
            "purchases": dict(list(purchases.items())[:limit]),
        }
        _log("retrieved relevant context")
        return result
