# API vs SDK Comparison Report

> Status: pending measured runs. The offline test suite passes, but neither a valid API benchmark nor an authenticated SDK benchmark has completed. The SDK attempt returned “Not logged in”; its invalid output artifact was removed. The API run was skipped because this terminal had no `ANTHROPIC_API_KEY`. Populate this report only from matching runs using the same scenario, model, effort, and external-search mode.

## Run metadata

| Field | API | SDK |
|---|---|---|
| Model | claude-opus-5-5 (configured; not run) | claude-opus-5-5 (configured; not authenticated) |
| Effort | medium (configured for API requests; not run) | medium (configured; not authenticated) |
| Dependency versions | See `requirements.txt` | See `requirements.txt` |
| Scenario | `scenario.json` (not run) | `scenario.json` (login failure before model use) |
| Search provider | Mock fixture by default (not run) | Mock fixture (no tool calls occurred) |

## Results summary

| Metric | API | SDK |
|---|---:|---:|
| Input tokens | Pending | Pending |
| Cache-read tokens | Pending / unavailable | Pending / unavailable |
| Cache-write tokens | Pending / unavailable | Pending / unavailable |
| Output tokens | Pending | Pending |
| Cache-read percentage | Pending / unavailable | Pending / unavailable |
| Model calls | Pending | Pending |
| Cost (USD) | Pending / unavailable | Pending / unavailable |
| Elapsed time | Pending | Pending |
| Checks passed | Not run | Not a valid run; login failure before any model/tool calls |

Cache-read percentage denominator: cache-read tokens divided by input tokens plus cache-read tokens. Use runtime-reported values only; do not infer missing values.

## Harness lines of code

Count nonblank, non-comment Python source lines per mapped responsibility. Count SDK replacement blocks by their `# replaces: <filename>` mapping. Record the counting command/method and exact source revision when filling this section.

| Responsibility | API LOC | SDK LOC |
|---|---:|---:|
| Loop / invocation | 112 | 199* |
| Tool dispatch / MCP tools | 207 | 173* |
| History | 28 | Shared adapter reuse; SDK runner adds orchestration |
| Memory | 5 | Shared memory reuse |
| Context | 14 | Shared context reuse |
| Compaction | 7 | SDK/CLI-managed; no dedicated equivalent module |
| Caching | 17 | SDK/CLI-managed; no explicit cache boundary |
| Token and cost metrics | 44 | SDK `ResultMessage` usage extraction in runner |

LOC method: API counts are nonblank, non-comment lines in the single-responsibility API harness files. The SDK runner is 199 lines, tool implementation is 173 lines, and agent configuration is 53 lines by the same rule; shared/reused functions are not counted twice. These are implementation-size indicators, not a strict one-to-one code comparison.

## Token and cache analysis

No comparable measurements. The SDK attempt stopped at the Claude Code login check; it produced no model usage, tool calls, or valid cost data. The invalid result artifact was removed. The API run was skipped because `ANTHROPIC_API_KEY` was unset. Do not draw token or cache conclusions from these attempts.

## Qualitative control comparison

| Area | API harness | SDK harness |
|---|---|---|
| Model/tool loop | Explicit `loop.py` loop, tool-use stop handling, batched tool-result message | Claude Code/SDK owns the loop and MCP dispatch |
| Tool errors | Harness serializes compact `is_error` results | In-process MCP handler errors are returned through SDK MCP behavior |
| History and memory | JSONL history adapter plus shared JSON memory store | Reuses the same adapters/store; creates a new SDK client per scenario session |
| Context selection | Shared topic-based memory selection and bounded history/compaction | Shared context selection; SDK/Claude Code may also add its own project context |
| Caching | Explicit API cache-control boundary helper | Cache placement is controlled by SDK/CLI/runtime rather than this harness |
| Instrumentation | Direct Messages API usage fields accumulated per call | ResultMessage-level usage/cost is available only when reported; no raw request-level cache guarantee |

These are implementation observations, not a measured cost recommendation. API gives finer control over transport and tool-result construction; SDK reduces orchestration code and integrates with Claude Code, while leaving more runtime behavior delegated.

## API control vs SDK delegation

Pending review against the measured implementation. The API harness explicitly owns its model/tool loop, batched tool-result messages, schema dispatch, error encoding, history writing, context assembly, compaction, cache boundaries, and token accumulation. The SDK delegates agent-loop and MCP transport behavior to Claude Code; document which corresponding controls or metrics are not exposed in the selected SDK version.

## Recommendation

Pending measured results and final validation. Base the choice on control, implementation effort, observability, reliability, safety, and cost—not token count alone.

## Limitations

- Product search currently uses the deterministic mock fixture and is not a live shopping search.
- Runtime-exposed cache and cost fields may differ between the API and SDK; unavailable values must remain labeled unavailable.
- No comparison should be claimed until both result files have been produced and the pass/fail checks reviewed.
