"""Offline tests for the explicit API tool loop and harness helpers."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from API.harness.history import append_message, load_session
from API.harness.loop import run_turn
from API.harness.tokens import TurnMetrics
from shared.domain import BridalProfile
from shared.memory import MemoryStore
from shared.search import MockSearchProvider


class FakeMessages:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self.responses)


class ApiHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.memory = MemoryStore(Path(self.directory.name) / "memory.json")
        self.profile = BridalProfile(
            wedding_date="2027-06-01",
            budget=2500,
            categories=("shoes", "accessories"),
        )
        self.provider = MockSearchProvider([])

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_multiple_tool_results_are_batched_into_one_user_message(self) -> None:
        client = SimpleNamespace(
            messages=FakeMessages(
                [
                    {
                        "stop_reason": "tool_use",
                        "content": [
                            {"type": "tool_use", "id": "t1", "name": "build_shopping_plan", "input": {"as_of": "2027-01-01"}},
                            {"type": "tool_use", "id": "t2", "name": "search_products", "input": {"query": "wedding shoes"}},
                        ],
                        "usage": {"input_tokens": 30, "output_tokens": 12},
                    },
                    {
                        "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": "Here is a plan."}],
                        "usage": {"input_tokens": 15, "output_tokens": 8, "cache_read_input_tokens": 4},
                    },
                ]
            )
        )
        metrics = TurnMetrics("session-1", 1)
        result = run_turn(
            client,
            model="test-model",
            system="test system",
            messages=[{"role": "user", "content": "Plan shoes"}],
            profile=self.profile,
            memory=self.memory,
            search_provider=self.provider,
            metrics=metrics,
        )
        tool_messages = [message for message in result["messages"] if message.get("role") == "user" and isinstance(message.get("content"), list)]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(len(tool_messages[0]["content"]), 2)
        self.assertEqual(metrics.model_calls, 2)
        self.assertEqual(metrics.input_tokens, 45)
        self.assertEqual(metrics.output_tokens, 20)
        self.assertEqual(metrics.cache_read_tokens, 4)
        self.assertEqual([tool["name"] for tool in metrics.tools], ["build_shopping_plan", "search_products"])
        self.assertEqual(client.messages.requests[0]["output_config"]["effort"], "medium")
        self.assertEqual(client.messages.requests[0]["model"], "test-model")

    def test_tool_error_is_returned_as_is_error_result_not_exception(self) -> None:
        client = SimpleNamespace(
            messages=FakeMessages(
                [
                    {
                        "stop_reason": "tool_use",
                        "content": [{"type": "tool_use", "id": "bad", "name": "not_a_tool", "input": {}}],
                        "usage": {},
                    },
                    {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Handled."}], "usage": {}},
                ]
            )
        )
        result = run_turn(
            client,
            model="test-model",
            system="test system",
            messages=[],
            profile=self.profile,
            memory=self.memory,
            search_provider=self.provider,
            metrics=TurnMetrics("session-1", 1),
        )
        tool_result = result["messages"][-1]["content"][0]
        self.assertTrue(tool_result["is_error"])
        self.assertIn("unknown tool", tool_result["content"])

    def test_history_is_append_only_and_session_scoped(self) -> None:
        path = Path(self.directory.name) / "history.jsonl"
        append_message(path, "one", {"role": "user", "content": "hello"})
        append_message(path, "two", {"role": "user", "content": "different session"})
        self.assertEqual(load_session(path, "one"), [{"role": "user", "content": "hello"}])
        self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)

    def test_metrics_are_json_serializable_and_cost_is_unavailable_by_default(self) -> None:
        metrics = TurnMetrics("session-1", 1)
        self.assertIsNone(metrics.cost_usd)
        json.dumps(metrics.to_dict())


if __name__ == "__main__":
    unittest.main()
