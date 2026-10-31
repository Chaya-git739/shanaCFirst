"""Offline validation of the shared two-session scenario and evaluator."""

import json
import unittest
from pathlib import Path

from shared.evaluation import evaluate_checks
from shared.memory import MemoryStore


ROOT = Path(__file__).resolve().parents[1]


class ScenarioTests(unittest.TestCase):
    def test_scenario_has_eight_turns_across_two_sessions(self) -> None:
        scenario = json.loads((ROOT / "scenario.json").read_text(encoding="utf-8"))
        sessions = scenario["sessions"]
        self.assertEqual(len(sessions), 2)
        self.assertTrue(all(len(session["turns"]) == 4 for session in sessions))
        self.assertEqual(sum(len(session["turns"]) for session in sessions), 8)
        self.assertEqual(len(scenario["checks"]), 10)

    def test_evaluator_checks_persisted_state_and_tool_evidence(self) -> None:
        scenario = json.loads((ROOT / "scenario.json").read_text(encoding="utf-8"))
        profile = {
            "budget": 1800,
            "purchased_categories": ["dress"],
        }
        decisions = {"selected_shoes": {"value": "shoe-002"}}
        turns = [
            {
                "tools": [
                    {
                        "name": "search_products",
                        "is_error": False,
                        "preview": '{"url":"https://shop.example.invalid/pearl-ivory-flat"}',
                    }
                ]
            }
            for _ in range(8)
        ]
        turns[2]["tools"].append(
            {
                "name": "save_profile",
                "is_error": False,
                "preview": '{"budget":{"saved_value":1800,"proposed_value":4300}}',
            }
        )
        results = evaluate_checks(
            scenario["checks"],
            profile=profile,
            decisions=decisions,
            purchases={},
            turns=turns,
        )
        self.assertEqual(len(results), 10)
        failed = [result for result in results if not result["passed"]]
        self.assertEqual(failed, [])

    def test_clean_state_memory_can_be_reopened_for_new_session(self) -> None:
        with __import__("tempfile").TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            first = MemoryStore(path)
            first.save_profile({"budget": 1800})
            second = MemoryStore(path)
            second.record_session("session-2")
            self.assertEqual(second.profile["budget"], 1800)
            self.assertIn("session-2", json.loads(path.read_text(encoding="utf-8"))["sessions"])


if __name__ == "__main__":
    unittest.main()
