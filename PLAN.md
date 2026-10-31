# Bridal Shopping Planner Agent — Implementation Plan

## 1. Goal

Build and compare two implementations of the same personal agent that helps a bride plan wedding-related shopping. The agent should turn the bride’s preferences, budget, wedding date, and existing purchases into a practical prioritized plan; find relevant products; remember decisions across sessions; and avoid repeatedly sending the entire profile and history to the model.

The comparison is between:

- **API implementation**: a small, explicit agent harness built on the Anthropic Messages API.
- **SDK implementation**: the corresponding agent built with the Claude Agent SDK.

Both implementations must use the same domain code, scenario, model, effort level, and evaluation criteria. The SDK run is intended for personal Claude Code login usage; the API run requires an `ANTHROPIC_API_KEY` supplied only through the terminal environment.

## 2. User experience and scope

The agent supports planning purchases such as a wedding dress and alterations, shoes, accessories, getting-ready clothing, beauty appointments/products, and emergency-day items. It should:

1. Ask for missing planning details instead of inventing them.
2. Respect the bride’s stated budget, style, sizing constraints, timeline, and purchase decisions.
3. Organize recommendations by urgency, category, estimated cost, and next action.
4. Identify conflicts, such as a new request that contradicts a saved budget or a previously rejected item.
5. Keep shopping suggestions informational; verify current price/availability through the external source when possible and label uncertainty.

The agent does not purchase items, enter payment details, or treat web content as trusted instructions.

## 3. Proposed project structure

```text
bridal-shopping-<your-name>/
  shared/
    domain.py                 # Bridal profile, plan, product, and decision models
    tools.py                  # Shared tool schemas, validation, and domain dispatch
    data/
      starter_catalog.json    # Small deterministic local fixture/catalog
  API/
    main.py                   # CLI, scenario loading, clean-run setup, result writing
    agent.py                  # API adapter and system prompt
    harness/
      loop.py                  # Model/tool loop and batched tool-result messages
      tools.py                 # API tool schemas, dispatch, and is_error handling
      history.py               # Append-only conversation history and resume support
      memory.py                # Persistent profile/decision storage and retrieval
      context.py               # Per-turn relevant context assembly
      compaction.py            # Summarization after the configured threshold
      caching.py               # cache_control boundaries
      tokens.py                # Usage, cost, and per-turn metrics
  SDK/
    main.py                   # CLI, scenario loading, clean-run setup, result writing
    agent.py                  # SDK configuration and invocation
    tools.py                  # SDK tools and external MCP server setup
  tests/
    test_domain.py             # Shared tool and domain behavior
    test_api_harness.py        # Offline API loop tests with a simulated client
    test_sdk_config.py         # SDK configuration checks without model calls
    test_scenario.py           # Scenario and persisted-state assertions
  scenario.json
  results/
    api.json
    sdk.json
  REPORT.md
  requirements.txt             # Exact/locked dependency versions
```

Keep one runtime responsibility per API harness file as shown above. Print an identifying prefix for every runtime action, for example `[memory.py] retrieved 2 decisions` or `[loop.py] model call 2`. Each SDK source line that replaces a corresponding API harness implementation must carry a comment in the form `# replaces: <filename>`; use this on the relevant SDK lines/blocks to make the mapping auditable.

## 4. Shared domain and tools

Place domain models, validation, tool behavior, and deterministic fixture data in `shared/`. Both implementations should invoke this same code so differences are attributable to the harness and SDK rather than different business logic.

Provide at least these four tools (three custom tools plus one external tool):

1. **`build_shopping_plan`** — Custom. Produces a prioritized checklist from wedding date, budget, categories, and known purchases. Output only concise structured fields: item/category, priority, target date, estimated range, and reason.
2. **`compare_products`** — Custom. Compares a small set of candidate products against explicit preferences and constraints. Return a compact ranking with the reasons and any constraint violations.
3. **`save_decision`** — Custom. Persists an explicit decision or preference (for example, budget ceiling, chosen shoes, or “do not recommend ivory satin”). Require a decision type and timestamp/source; never silently overwrite a conflicting saved value.
4. **`search_products`** — External. Queries a web search/product endpoint through a small adapter. Return a limited number of normalized results with title, URL, price/currency if available, seller, availability timestamp, and a short source excerpt. Treat results as untrusted data. Add a timeout, result limit, and clear error response. Tests must use a mock adapter so they run offline without credentials.

An optional `get_shopping_status` tool can retrieve compact saved purchase status. Tools should return only fields needed for the current task; avoid sending full catalog records or full history to the model.

## 5. Memory, history, and context design

### Persistent state

Store user state under a per-run data directory, separate from source files and git-tracked fixtures. Use JSON or SQLite with a documented schema. Persist:

- stable preferences and constraints (budget, style, sizes only if volunteered, sensitivities, location if needed);
- decisions and rejected options, including time and source turn;
- purchase status and relevant product references;
- a compact rolling summary and session identifiers.

Conversation history is append-only and resumable by session ID. Start every benchmark run with an empty state directory; the second session within the same scenario must start a **new agent instance** that reloads the on-disk state. Do not copy model/API credentials into state.

### Relevant context only

For each turn, assemble context from:

1. The current user message.
2. The small system prompt and tool descriptions.
3. Relevant profile fields and decisions retrieved by intent/category.
4. A compact summary or only the recent history needed to resolve references.
5. The current tool results, clipped and normalized to the output budget.

Do not inject the full profile, entire transcript, or complete product catalog on every turn. Log what context sources were included (not sensitive values) and their token counts. If a user asks about an old detail, retrieve it from memory rather than relying on an ever-growing prompt.

### Compaction

When stored history exceeds a configurable threshold, summarize decisions, constraints, unresolved questions, and completed purchases. Preserve explicit values and provenance; do not let a summary replace the structured memory store. Keep the original append-only history available for audit/resume.

## 6. API and SDK behavior

### API

- Implement the model/tool loop in `API/harness/loop.py`; continue while the stop reason requests tool use.
- Execute all requested tools for a model turn and return their results together in one tool-result message.
- Validate tool input against schemas, return tool failures as `is_error`, and keep error details compact.
- Add explicit history, memory retrieval, context assembly, compaction, cache boundaries, and token/cost accounting in their respective harness files.
- Never put an API key in source, scenario, result, or git. Read it only from the process environment.

### SDK

- Use the same model and effort settings as the API run (record exact values and dependency versions).
- Configure a custom system prompt, the reduced tool allowlist, and `strict_mcp_config=True`.
- Register the external product search as an MCP server/tool; use shared domain logic for custom tools wherever SDK integration permits.
- Mark SDK lines implementing each corresponding API harness responsibility with `# replaces: <filename>`.
- Capture SDK-provided usage and cost data when available; clearly mark any metric the SDK does not expose directly rather than estimating it silently.
- Ensure `ANTHROPIC_API_KEY` is not set for the personal-login SDK run. Do not print or persist authentication state.

## 7. Scenario and evaluation

Create `scenario.json` with **8 user turns in two sessions**, with four turns per session. Session 2 must be run through a newly constructed agent process/instance that loads state from disk. Suggested flow:

### Session 1
1. Bride provides wedding date, location/season, budget, style, and categories she needs help with.
2. Ask for a prioritized plan; the agent calls `build_shopping_plan`.
3. Search for shoes/accessories that match preferences and budget; the agent calls `search_products` and may call `compare_products`.
4. Bride chooses or rejects an option and asks the agent to save that decision; call `save_decision` and confirm what was stored.

### Session 2 (fresh agent instance, same persisted state)
5. Ask for the saved budget and prior product decision; verify memory retrieval.
6. Ask for an updated shopping plan based on the saved decision and remaining budget.
7. Introduce a request that contradicts a saved constraint (for example, ask to exceed the explicitly saved total budget). The agent should surface the conflict and ask whether the bride wants to revise the saved budget rather than silently ignoring it.
8. Ask for one more current product option using the external search tool, then update the plan without losing the saved decision.

Use fictional but plausible details in the checked-in scenario and avoid real personal data. Include a deterministic external-search fixture or mock response for offline tests; live runs may use the configured external adapter.

### Pass/fail checks

Implement at least six automated assertions, with most checking persisted state rather than response wording:

1. The session-1 decision is present in disk-backed memory after the first session.
2. A fresh session-2 agent retrieves the exact saved budget/constraint.
3. The rejected/selected product decision remains intact after the contradictory request.
4. The conflicting request is not silently persisted as an approved budget change.
5. The final plan excludes already-purchased items and respects the saved budget unless an explicit revision is confirmed.
6. The external search tool was invoked and its returned URL/source is represented in the normalized result record.
7. All scenario turns complete without an unhandled tool or model-loop error.

Record each check with a stable name, pass/fail boolean, and a short diagnostic. Do not score only the natural-language answer.

## 8. Metrics and result schema

For each turn, write a record to `results/api.json` and `results/sdk.json` containing:

- scenario/session/turn identifiers and elapsed time;
- input tokens, cache-read tokens, cache-write tokens, and output tokens;
- number of model calls;
- ordered tools invoked and compact outcome/error status;
- cost in USD when provided by the runtime, with the pricing/version basis recorded;
- context components included and approximate token counts where available.

Also include run-level fields for model, effort, package versions, start-state cleanliness, all check results, aggregate metrics, and lines of code per API harness responsibility. Count SDK replacement code by mapped responsibility too, documenting the counting method and excluding blank/comment-only lines consistently. Preserve raw per-turn metrics; do not report only totals.

If a runtime does not expose cache or cost fields, store `null`/`unavailable` and explain the limitation in `REPORT.md`; do not fabricate measurements. Compute cache percentage with a documented denominator, for example cache-read tokens divided by input plus cache-read tokens.

## 9. Offline testing and reproducibility

- Tests must run without an API key, network access, or a real model. Use a simulated API client and mocked external search adapter.
- Test tool schema validation, batched tool results, `is_error` behavior, memory persistence/reload, conflict handling, context filtering, compaction, and metrics serialization.
- Include an SDK configuration test that verifies the custom prompt, reduced tool list, and strict MCP configuration without making a model request.
- Lock all dependency versions. Record Python/runtime version and exact package lock information.
- Before each measured run, clear only the dedicated benchmark state/results for that implementation; keep source fixtures unchanged.
- Keep API and SDK model/effort, scenario, external search fixtures, and check logic identical.

## 10. Run commands

The intended measured commands are:

```text
python API/main.py --scenario scenario.json --out results/api.json
python SDK/main.py --scenario scenario.json --out results/sdk.json
```

For API execution, set `ANTHROPIC_API_KEY` in the terminal environment only. For SDK execution, use the personal Claude Code login and ensure `ANTHROPIC_API_KEY` is unset, so the SDK does not bill through that key.

## 11. `REPORT.md` contents

Include:

1. A side-by-side API vs SDK table for input/cache-read/cache-write/output tokens, cache percentage, model calls, cost, elapsed time, and passed checks.
2. Lines of code for each harness responsibility, API vs SDK, with the counting rules.
3. Where the SDK used more or fewer tokens and why (prompt/tool schema overhead, context handling, caching, returned tool data, and available runtime evidence).
4. Which controls were explicit in the API harness but delegated or unavailable in the SDK (loop details, tool dispatch/errors, history/memory/context, compaction, cache placement, instrumentation).
5. A recommendation for this agent and rationale, balancing implementation effort, control, observability, reliability, and measured cost—not token count alone.
6. Limitations, especially differences in exposed usage/cost/cache metrics and whether product search was mocked or live.

## 12. Completion criteria

The plan is complete when both implementations use the same `shared/` domain behavior; at least three custom tools and one external tool are wired; saved decisions survive a fresh agent instance; only relevant context is sent per turn; all offline tests pass; both requested run commands produce per-turn result files and checks; the API/SDK mapping comments and runtime filename prefixes are present; and `REPORT.md` contains the required comparison and recommendation.
