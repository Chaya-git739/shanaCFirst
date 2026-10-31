"""Offline persistence, conflict, and selective retrieval tests."""

import json
import tempfile
import unittest
from pathlib import Path

from shared.domain import ShoppingDecision
from shared.memory import MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def test_decision_survives_fresh_store_instance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "memory.json"
            first = MemoryStore(path)
            result = first.save_decision(
                ShoppingDecision("shoe_choice", "shoe-002", "2026-10-31T12:00:00Z", "scenario:4")
            )
            self.assertEqual(result["status"], "saved")

            second = MemoryStore(path)
            loaded = second.decisions["shoe_choice"]
            self.assertEqual(loaded.value, "shoe-002")
            self.assertEqual(loaded.source, "scenario:4")

    def test_conflicting_decision_is_not_persisted_without_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            store = MemoryStore(path)
            store.save_decision(
                ShoppingDecision("budget", 1500, "2026-10-31T12:00:00Z", "scenario:1")
            )
            conflict = store.save_decision(
                ShoppingDecision("budget", 2000, "2026-10-31T12:05:00Z", "scenario:7")
            )
            self.assertEqual(conflict["status"], "conflict")
            self.assertEqual(MemoryStore(path).decisions["budget"].value, 1500)

    def test_profile_conflict_does_not_replace_saved_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            store = MemoryStore(path)
            store.save_profile({"budget": 1500, "style": "classic"})
            conflict = store.save_profile({"budget": 2000})
            self.assertEqual(conflict["status"], "conflict")
            self.assertEqual(MemoryStore(path).profile["budget"], 1500)

    def test_context_retrieval_returns_only_relevant_compact_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            store = MemoryStore(path)
            store.save_profile({"budget": 1500, "style": "classic", "shoe_color": "ivory"})
            store.save_decision(
                ShoppingDecision("shoe_choice", "shoe-002", "2026-10-31T12:00:00Z", "scenario:4")
            )
            store.save_purchase("dress", "purchased", product_id="dress-9")
            context = store.get_relevant_context("shoe", limit=2)
            self.assertEqual(context["profile"], {"shoe_color": "ivory"})
            self.assertIn("shoe_choice", context["decisions"])
            self.assertEqual(context["purchases"], {})
            self.assertLess(len(json.dumps(context)), 1000)

    def test_memory_state_contains_no_unrequested_history_or_secret_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            store = MemoryStore(path)
            store.save_profile({"budget": 1500})
            store.record_session("session-1")
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["sessions"], ["session-1"])
            self.assertNotIn("api_key", raw)
            self.assertNotIn("messages", raw)


if __name__ == "__main__":
    unittest.main()
