"""CLI entry point for running the bridal-shopping planner API harness."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from API.agent import EFFORT, MODEL, create_client, system_prompt
from API.harness.context import build_context
from API.harness.compaction import compact_if_needed
from API.harness.history import append_message, load_session
from API.harness.loop import run_turn
from API.harness.memory import open_memory
from API.harness.tokens import TurnMetrics
from shared.search import MockSearchProvider
from shared.domain import BridalProfile
from shared.evaluation import evaluate_checks


def run_scenario(
    scenario_path: str | Path,
    output_path: str | Path,
    *,
    client: Any,
) -> dict[str, Any]:
    scenario = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    run_dir = Path(output_path).parent / "api_state"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    provider = MockSearchProvider(scenario.get("search_fixture", []))
    turns: list[dict[str, Any]] = []

    for session in scenario["sessions"]:
        session_id = session["id"]
        # Construct a new profile/memory view for each session; later sessions reload disk state.
        memory = open_memory(run_dir / "memory.json")
        memory.record_session(session_id)
        for turn_number, turn in enumerate(session["turns"], start=1):
            profile_data = dict(memory.profile)
            proposed_updates = turn.get("profile_updates", {})
            if proposed_updates:
                saved = memory.save_profile(proposed_updates)
                if saved["status"] == "conflict":
                    raise ValueError("Scenario attempted to overwrite saved profile data without confirmation")
                profile_data = dict(memory.profile)
            if "wedding_date" not in profile_data or "budget" not in profile_data:
                raise ValueError("Profile requires wedding_date and budget before model turns")
            profile = BridalProfile(
                wedding_date=profile_data["wedding_date"],
                budget=profile_data["budget"],
                currency=profile_data.get("currency", "USD"),
                categories=tuple(profile_data.get("categories", ())),
                purchased_categories=tuple(profile_data.get("purchased_categories", ())) + tuple(
                    category
                    for category, purchase in memory.purchases.items()
                    if isinstance(purchase, dict)
                    and purchase.get("status") == "purchased"
                    and category not in profile_data.get("purchased_categories", ())
                ),
                style_preferences=tuple(profile_data.get("style_preferences", ())),
                avoid_terms=tuple(profile_data.get("avoid_terms", ())),
            )
            message = {"role": "user", "content": turn["message"]}
            append_message(run_dir / "history.jsonl", session_id, message)
            history = load_session(run_dir / "history.jsonl", session_id)
            compacted_history = compact_if_needed(history[:-1])
            relevant_history = list(compacted_history["recent_history"])
            if compacted_history["summary"]:
                relevant_history.insert(
                    0,
                    {"role": "system", "content": "Earlier conversation summary: " + compacted_history["summary"]},
                )
            context = build_context(turn["message"], memory, recent_history=relevant_history)
            context_payload = json.dumps(context, ensure_ascii=False)
            messages = [{"role": "user", "content": context_payload}]
            metrics = TurnMetrics(session_id=session_id, turn=turn_number)
            started = time.perf_counter()
            result = run_turn(
                client,
                model=MODEL,
                system=system_prompt(),
                messages=messages,
                profile=profile,
                memory=memory,
                search_provider=provider,
                metrics=metrics,
                on_message=lambda item: append_message(run_dir / "history.jsonl", session_id, item),
            )
            metrics.elapsed_ms = max(metrics.elapsed_ms, (time.perf_counter() - started) * 1000)
            response = result["response"]
            output_text = _extract_text(response)
            turn_record = metrics.to_dict()
            turn_record.update(
                {
                    "turn": turn.get("id", turn_number),
                    "output": output_text,
                    "context": {
                        "included_sources": context["included_sources"],
                        "approx_tokens": max(1, len(context_payload) // 4),
                    },
                }
            )
            turns.append(turn_record)

    checks = evaluate_checks(
        scenario.get("checks", []),
        profile=memory.profile,
        decisions=memory.decisions,
        purchases=memory.purchases,
        turns=turns,
    )
    result_document = {
        "implementation": "API",
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
        "cost_basis": "Runtime-reported only; null when unavailable.",
        "start_state_clean": True,
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result_document, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[main.py] wrote API run results")
    return result_document


def _extract_text(response: Any) -> str:
    content = response.get("content", []) if isinstance(response, dict) else getattr(response, "content", [])
    return "\n".join(
        str(block.get("text", "") if isinstance(block, dict) else getattr(block, "text", ""))
        for block in content
        if (block.get("type") if isinstance(block, dict) else getattr(block, "type", None)) == "text"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run_scenario(args.scenario, args.out, client=create_client())


if __name__ == "__main__":
    main()
