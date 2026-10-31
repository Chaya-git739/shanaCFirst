# Bridal Shopping Planner Agent

A small project comparing an explicit Anthropic Messages API harness with the Claude Agent SDK for a bridal shopping-planning assistant. Shared domain rules, memory, product normalization, and scenario checks live in `shared/` and are used by both implementations.

## Requirements

- Python 3.10 or later.
- Install pinned dependencies from `requirements.txt` for live model runs.
- Offline tests use the Python standard library and do not require model credentials, network access, or the SDK package.
- API run: set `ANTHROPIC_API_KEY` in the terminal environment only.
- SDK run: authenticate through Claude Code login and ensure `ANTHROPIC_API_KEY` is unset, so the SDK does not switch to API-key billing.
- The SDK runner refuses to write a benchmark result if a turn reports an error or no model turn completed; authenticate with `/login` before running it.

## Offline tests

Run from the project root:

```text
python -m unittest discover -s tests -v
```

The tests use a simulated model client and a deterministic search fixture.

## Scenario runs

The checked-in `scenario.json` contains eight fictional turns over two sessions. Each runner clears its own state directory before a run; session 2 creates a new agent/client instance and reloads the persistent state file. Run from the project root:

```text
python API/main.py --scenario scenario.json --out results/api.json
python SDK/main.py --scenario scenario.json --out results/sdk.json
```

The API command requires a Console key available in `ANTHROPIC_API_KEY`. For the SDK command, use Claude Code login and do not leave `ANTHROPIC_API_KEY` set. Product search currently uses the scenario's mock provider; results are marked external/unverified test data, not live listings.

Each output includes per-turn usage, elapsed time, model calls, tools, checks, and aggregate metrics. SDK cache/token/cost fields are populated only when the SDK runtime reports them; unknown fields remain null or zero as appropriate. Do not compare benchmark values unless both runs use the same model, effort, scenario, and provider mode.

## State and privacy

Runtime memory/history is written beneath `results/api_state/` or `results/sdk_state/` and should not be committed. The scenario and starter catalog use fictional data. Never store an API key in source, scenario, or results files.

## Current limitations

- External product search is a deterministic mock; select and configure a live provider before production use.
- The SDK and API do not expose identical usage/cache metrics. Check each result's `cost_basis` and per-turn availability before drawing conclusions.
- `REPORT.md` is produced after comparable measured runs; do not infer relative cost from the test fixture.
