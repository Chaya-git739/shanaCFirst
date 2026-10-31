"""Offline tests for turn-context selection and history compaction."""

import tempfile
import unittest
from pathlib import Path

from shared.compaction import compact_history
from shared.context import assemble_turn_context, classify_turn, compact_tool_result
from shared.domain import ShoppingDecision
from shared.memory import MemoryStore


class ContextTests(unittest.TestCase):
    def test_classifier_extracts_relevant_topics(self) -> None:
        self.assertEqual(classify_turn("What shoes fit my budget?"), {"budget", "product"})

    def test_context_uses_only_relevant_memory_and_recent_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            memory = MemoryStore(Path(directory) / "memory.json")
            memory.save_profile({"budget": 1800, "style": "classic", "shoe_color": "ivory"})
            memory.save_decision(
                ShoppingDecision("shoe_choice", "shoe-002", "2026-10-31T12:00:00Z", "scenario:4")
            )
            context = assemble_turn_context(
                "Find shoes under budget",
                memory,
                recent_history=[
                    {"role": "user", "content": "old turn"},
                    {"role": "assistant", "content": "recent answer"},
                ],
                history_limit=1,
            )
            self.assertEqual(context["recent_history"], [{"role": "assistant", "content": "recent answer"}])
            self.assertIn("budget", context["memory"]["profile"])
            self.assertEqual(context["memory"]["profile"], {"budget": 1800})
            self.assertIn("relevant_memory", context["included_sources"])

    def test_context_without_topic_matches_omits_unrelated_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            memory = MemoryStore(Path(directory) / "memory.json")
            memory.save_profile({"style": "classic"})
            result = assemble_turn_context("Hello", memory)
            self.assertEqual(result["memory"], {"profile": {}, "decisions": {}, "purchases": {}})
            self.assertNotIn("relevant_memory", result["included_sources"])

    def test_compaction_preserves_recent_history_and_bounds_summary(self) -> None:
        history = [{"role": "user", "content": f"message {index} " + "x" * 80} for index in range(8)]
        result = compact_history(history, max_messages=4, keep_recent=2, max_summary_chars=100)
        self.assertTrue(result["compacted"])
        self.assertEqual(result["recent_history"], history[-2:])
        self.assertLessEqual(len(result["summary"]), 100)
        below_threshold = compact_history(history[-3:], max_messages=4)
        self.assertFalse(below_threshold["compacted"])

    def test_tool_result_compaction_limits_lists_strings_and_payload(self) -> None:
        result = compact_tool_result(
            {"status": "ok", "results": [{"title": "x" * 200} for _ in range(20)]},
            max_chars=90,
            max_items=2,
        )
        self.assertEqual(result, {"status": "ok", "truncated": True})
        compact = compact_tool_result({"results": list(range(20))}, max_chars=200, max_items=3)
        self.assertEqual(compact["results"], [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
