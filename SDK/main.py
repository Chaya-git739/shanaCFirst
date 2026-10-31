"""Scenario runner for the Claude Agent SDK bridal-shopping agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from SDK.agent import EFFORT, MODEL, create_options
from API.harness.history import append_message  # replaces: history.py
from API.harness.tokens import TurnMetrics  # replaces: tokens.py
from shared.context import assemble_turn_context
from shared.domain import BridalProfile
from shared.memory import MemoryStore
from shared.search import MockSearchProvider
from shared.evaluation import evaluate_checks


def _profile_from_memory(memory: MemoryStore, updates: dict[str, Any]) -> BridalProfile:
    data = memory.profile
    data.update(updates)
    if "wedding_date" not in data or "budget" not in data:
        raise ValueError("Profile requires wedding_date and budget before model turns")
    return BridalProfile(
        wedding_date=data["wedding_date"],
        budget=data["budget"],
        currency=data.get("currency", "USD"),
        categories=tuple(data.get("categories", ())),
        purchased_categories=tuple(data.get("purchased_categories", ())),
        style_preferences=tuple(data.get("style_preferences", ())),
        avoid_terms=tuple(data.get("avoid_terms", ())),
    )


def _result_usage(message: Any) -> dict[str, int | float | None]:
    model_usage = getattr(message, "model_usage", None) or {}
    totals: dict[str, int | float | None] = {
        "input": 0,
        "cache_read": 0,
        "cache_write": 0,
        "output": 0,
    }
    for usage in model_usage.values():
        totals["input"] = int(totals["input"] or 0) + int(usage.get("inputTokens", 0) or 0)
        totals["cache_read"] = int(totals["cache_read"] or 0) + int(usage.get("cacheReadInputTokens", 0) or 0)
        totals["cache_write"] = int(totals["cache_write"] or 0) + int(usage.get("cacheCreationInputTokens", 0) or 0)
        totals["output"] = int(totals["output"] or 0) + int(usage.get("outputTokens", 0) or 0)
    totals["cost_usd"] = getattr(message, "total_cost_usd", None)
    if totals["cost_usd"] == 0 and not any(
        totals[key] for key in ("input", "cache_read", "cache_write", "output")
    ):
        totals["cost_usd"] = None
    return totals


async def run_scenario(scenario_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    if os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Unset ANTHROPIC_API_KEY before SDK run; use Claude Code login billing")
    try:
        from claude_agent_sdk import AssistantMessage, ClaudeSDKClient, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage
    except ImportError as exc:
        raise RuntimeError("Install claude-agent-sdk to run the SDK agent") from exc

    scenario = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    run_dir = Path(output_path).parent / "sdk_state"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    provider = MockSearchProvider(scenario.get("search_fixture", []))
    turns: list[dict[str, Any]] = []

    for session in scenario["sessions"]:
        session_id = session["id"]
        # A separate client and MCP tool closure makes each session a fresh agent instance.
        memory = MemoryStore(run_dir / "memory.json")  # replaces: memory.py
        memory.record_session(session_id)
        first_updates = session["turns"][0].get("profile_updates", {}) if session.get("turns") else {}
        if first_updates:
            memory.save_profile(first_updates)
        session_profile = _profile_from_memory(memory, {})
        async with ClaudeSDKClient(
            options=create_options(
                session_profile,
                memory,
                provider,
                cwd=str(Path(scenario_path).resolve().parent),
            )
        ) as client:
            previous_usage = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "cost_usd": 0.0}
            history_path = run_dir / "history.jsonl"
            for turn_number, turn in enumerate(session["turns"], start=1):
                updates = turn.get("profile_updates", {})
                if updates and turn_number != 1:
                    memory.save_profile(updates)
                profile = _profile_from_memory(memory, {})
                existing_history = []
                context = assemble_turn_context(turn["message"], memory, recent_history=existing_history)  # replaces: context.py
                prompt = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
                append_message(history_path, session_id, {"role": "user", "content": turn["message"]})
                metrics = TurnMetrics(session_id=session_id, turn=turn_number)
                tool_records: list[dict[str, Any]] = []
                tool_names_by_id: dict[str, str] = {}
                response_text: list[str] = []
                last_result: Any = None
                started = time.perf_counter()
                print(f"[main.py] SDK turn {session_id}:{turn_number}")
                await client.query(prompt)  # replaces: loop.py
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                response_text.append(block.text)
                            elif isinstance(block, ToolUseBlock):
                                tool_name = block.name.split("__")[-1]
                                tool_names_by_id[block.id] = tool_name
                                tool_records.append({"name": tool_name, "is_error": False, "preview": ""})
                    elif isinstance(message, UserMessage):
                        for block in message.content:
                            if isinstance(block, ToolResultBlock):
                                tool_name = tool_names_by_id.get(block.tool_use_id)
                                for tool_record in reversed(tool_records):
                                    if tool_record["name"] == tool_name and not tool_record["preview"]:
                                        tool_record["is_error"] = bool(block.is_error)
                                        preview = str(block.content or "")
                                        tool_record["preview"] = preview[:600]
                                        break
                    elif isinstance(message, ResultMessage):
                        last_result = message
                        metrics.model_calls += int(getattr(message, "num_turns", 0) or 0)
                metrics.elapsed_ms = (time.perf_counter() - started) * 1000
                metrics.tools = tool_records
                current_usage = _result_usage(last_result) if last_result is not None else {}
                for key, metric_key in (("input", "input_tokens"), ("cache_read", "cache_read_tokens"), ("cache_write", "cache_write_tokens"), ("output", "output_tokens")):
                    current = int(current_usage.get(key, 0) or 0)
                    before = int(previous_usage.get(key, 0) or 0)
                    setattr(metrics, metric_key, max(0, current - before))
                    previous_usage[key] = current
                cumulative_cost = current_usage.get("cost_usd")
                if cumulative_cost is not None:
                    metrics.cost_usd = max(0.0, float(cumulative_cost) - float(previous_usage.get("cost_usd", 0.0) or 0.0))
                    previous_usage["cost_usd"] = float(cumulative_cost)
                output_text = "\n".join(response_text)
                if last_result is not None and getattr(last_result, "is_error", False):
                    raise RuntimeError(f"SDK turn failed ({getattr(last_result, 'subtype', 'unknown')})")
                if not metrics.model_calls:
                    raise RuntimeError("SDK returned no completed model turn")
                append_message(history_path, session_id, {"role": "assistant", "content": output_text})  # replaces: history.py
                record = metrics.to_dict()
                record.update(
                    {
                        "turn": turn.get("id", turn_number),
                        "output": output_text,
                        "context": {
                            "included_sources": context["included_sources"],
                            "approx_tokens": max(1, len(prompt) // 4),
                        },
                        "cost_reported_by_sdk": metrics.cost_usd is not None,
                    }
                )
                turns.append(record)

    if not any(turn["model_calls"] for turn in turns):
        raise RuntimeError("SDK run produced no model calls; authenticate with Claude Code /login and rerun")

    final_memory = MemoryStore(run_dir / "memory.json")
    checks = evaluate_checks(
        scenario.get("checks", []),
        profile=final_memory.profile,
        decisions=final_memory.decisions,
        purchases=final_memory.purchases,
        turns=turns,
    )
    result_document = {
        "implementation": "SDK",
        "model": MODEL,
        "effort": EFFORT,
        "turns": turns,
        "checks": checks,
        "aggregate": {
            "input_tokens": sum(turn["tokens"]["input"] for turn in turns),
            "cache_read_tokens": sum(turn["tokens"]["cache_read"] for turn in turns),
            "cache_write_tokens": sum(turn["tokens"]["cache_write"] for turn in turns),
            "output_tokens": sum(turn["tokens"]["output"] for turn in turns),
            "model_calls": sum(turn["model_calls"] for turn in turns),
            "cost_usd": sum(turn["cost_usd"] or 0 for turn in turns) if any(turn["cost_usd"] is not None for turn in turns) else None,
            "elapsed_ms": round(sum(turn["elapsed_ms"] for turn in turns), 3),
            "checks_passed": sum(check["passed"] for check in checks),
            "checks_total": len(checks),
        },
        "cost_basis": "Per-turn delta of SDK-reported cumulative cost; null when unavailable.",
        "start_state_clean": True,
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result_document, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[main.py] wrote SDK run results")
    return result_document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    asyncio.run(run_scenario(args.scenario, args.out))


if __name__ == "__main__":
    main()
