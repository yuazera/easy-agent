# Test Results

## Snapshot Policy

- Release `0.3.5` publishes benchmark, public-eval, Python verification, and real-network snapshots refreshed on April 14, 2026.
- The latest unreleased verification refresh on April 20, 2026 keeps the April 14 benchmark and headline public-eval score snapshot, while refreshing Python verification, live provider compatibility, and the real-network suite.
- Public docs in this repository intentionally expose methodology and scores only; local collaboration logs are not part of the repository-facing surface.

## Benchmark Snapshot

| Test Set | Score | Avg Duration (s) |
| --- | ---: | ---: |
| benchmark.single_agent | 100.0 | 5.0674 |
| benchmark.sub_agent | 100.0 | 59.2087 |
| benchmark.multi_agent_graph | 100.0 | 12.6349 |
| benchmark.team_round_robin | 100.0 | 9.9354 |
| benchmark.team_selector | 100.0 | 13.9754 |
| benchmark.team_swarm | 100.0 | 11.7101 |

## Public Eval Snapshot

| Test Set | Score | Avg Duration (s) |
| --- | ---: | ---: |
| public_eval.bfcl_simple | 100.0 | 5.0554 |
| public_eval.bfcl_multiple | 100.0 | 6.3535 |
| public_eval.bfcl_parallel_multiple | 100.0 | 8.7009 |
| public_eval.bfcl_irrelevance | 100.0 | 4.3747 |
| public_eval.bfcl_web_search | 100.0 | 6.9273 |
| public_eval.bfcl_memory | 100.0 | 3.9823 |
| public_eval.bfcl_format_sensitivity | 100.0 | 4.1343 |
| public_eval.tau2_mock | 100.0 | 4.9205 |

Current headline scores:

| Category | Score |
| --- | ---: |
| public_eval.bfcl_overall | 100.0 |
| public_eval.bfcl_case_pass_rate | 100.0 |
| public_eval.bfcl_core | 100.0 |
| public_eval.bfcl_agentic | 100.0 |
| public_eval.tau2_mock | 100.0 |

Scoring notes:

- `public_eval.bfcl_overall` is the official-style subcategory accuracy over the BFCL suites currently evaluated in this repository scope. It is not the raw case pass rate.
- `public_eval.bfcl_case_pass_rate` remains available as a diagnostic metric for individual-case success.
- `public_eval.bfcl_web_search` is tracked as normalized final-answer accuracy, with tool-call match rates kept as diagnostic signals.
- The repo-pinned `full_v4` BFCL slice is fully green in this snapshot, including the core multi-tool cases plus the added search-plus-contents and memory-backed cases.
- Raw `official_full_v4` manifests are normalized from JSON or JSONL inputs before filtering and execution, without switching the README headline score away from the repo-pinned baseline.
- The provider compatibility matrix covers OpenAI-compatible chat-completions and Responses API payload or parsing parity on top of the strict function-calling baseline.
- MCP catalog durability includes `resource_templates`, prompt-detail cache entries, and notification-driven stale marking.

Web-search diagnostics from the April 14, 2026 release refresh:

| Metric | Value |
| --- | ---: |
| web_search.content_sources.cache | 0 |
| web_search.content_sources.network | 0 |
| web_search.content_sources.replay | 2 |
| web_search.grounded_retry_count | 0 |
| web_search.grounded_sources_average | 1.4 |

Interpretation notes:

- This release keeps the repo-pinned BFCL web-search slice green while exposing the search or contents source mix separately from the headline pass rate.
- On this machine, the release refresh completed through replay-backed BFCL web-search evidence rather than live SerpApi results, which is reflected in the published diagnostics instead of being hidden behind a simple pass.

## Provider Compatibility Live Verification

This matrix is the latest April 20, 2026 live verification pass, separate from the retained April 14 benchmark and headline public-eval score snapshot.

| Target | Status | Notes |
| --- | --- | --- |
| openai_live | passed | Required DeepSeek/OpenAI-compatible baseline passed on `chat_completions`; strict-schema, `tool_choice: none`, required-tool, and forced-tool checks all passed. |
| anthropic_live | skipped | Optional target; no local `ANTHROPIC_API_KEY` was present in this verification pass. |
| gemini_live | skipped | Optional target; no local `GEMINI_API_KEY` was present in this verification pass. |

Compatibility notes:

- `single_tool_call_control` is now reported as `best_effort` for non-OpenAI OpenAI-compatible providers instead of incorrectly failing the whole provider row when the field is exposed but not enforced strictly at runtime.
- BFCL web-search query arguments now support the `x-easy-agent-normalizer: web_search_query` path so wrapper text can be normalized before scoring without weakening exact answer checks.

## Real-Network Snapshot

Latest generated snapshot timestamp: `2026-04-20T09:27:57Z`

| Test Set | Score | Duration (s) | Notes |
| --- | ---: | ---: | --- |
| real_network.cross_process_federation | 100.0 | 1.9705 | well-known discovery and send/poll federation |
| real_network.live_model_federation_roundtrip | 100.0 | 12.1822 | loopback federation through the local A2A surface |
| real_network.disconnect_retry_chaos | 100.0 | 6.7505 | callback retry, push notifications, and signed webhook delivery |
| real_network.duplicate_delivery_replay_resilience | 100.0 | 4.8176 | replay-safe callback and durable task events |
| real_network.workbench_reuse_process | 100.0 | 2.0720 | process workbench reuse |
| real_network.workbench_reuse_container | 100.0 | 35.3183 | container warm-start and snapshot restore |
| real_network.workbench_incremental_snapshot_reuse_container | 100.0 | 57.5803 | incremental container snapshot reuse |
| real_network.workbench_reuse_microvm | 100.0 | 25.5402 | SSH-backed microVM reuse |
| real_network.workbench_incremental_snapshot_reuse_microvm | 100.0 | 36.1659 | incremental microVM snapshot reuse |
| real_network.replay_resume_failure_injection | 100.0 | 8.0164 | replay/resume failure injection |

Warm-start telemetry summary:

| Metric | Value |
| --- | ---: |
| telemetry.cache_hit_rate | 100.0 |
| telemetry.container_warm_start_average_seconds | 6.5787 |
| telemetry.microvm_warm_start_average_seconds | 10.7598 |
| telemetry.snapshot_drift_ratio_average | 0.4047 |
| telemetry.snapshot_drift_ratio_max | 0.5943 |

## Similar Agent Project Comparison

The README keeps the comparison high level. This page keeps the public evidence mapping.

| Project | Evidence Basis | Sessions / Memory | Replay / Resume | Tool Calling | Isolation | Public Evals |
| --- | --- | --- | --- | --- | --- | --- |
| easy-agent | repo-local tested evidence | session_id + session_messages + session_state + harness_state | resume, replay, fork, checkpoints | strict function calling + SerpApi web-search eval + provider schema matrix | process / container / microvm | BFCL + tau2 + real-network telemetry |
| OpenHands | official docs mapping | conversation and state surfaces documented | persistent task continuation documented, not a replay-first runtime | coding-agent tool and browser actions documented | sandbox/runtime isolation documented | no BFCL-style built-in public eval matrix in docs |
| Skyvern | official docs mapping | workflow and run history documented | workflow rerun and recovery documented, less checkpoint-centric | browser and action execution documented | hosted browser/runtime boundary documented | no BFCL-style public eval matrix in docs |
| AutoGPT Platform | official docs mapping | agents, workflows, and run state documented | workflow reruns documented, not a graph replay runtime | agent blocks and integrations documented | platform execution boundary documented | no BFCL-style built-in public eval matrix in docs |

## Python Verification

This round uses Python-based verification only.

- Static checks: `ruff` and `mypy`
- Targeted regressions around provider compatibility, config validation, guardrails, and BFCL evaluation: `89 passed`
- Full unit coverage: `196 passed`
- Targeted live provider-compatibility regression: `1 passed`
- Full real integration coverage: `7 passed`, `2 warnings`
- The retained benchmark and headline public-eval scores still point at the April 14 release snapshot, while the real-network artifact and live provider-compatibility evidence were refreshed on April 20
- The remaining warnings are known Windows asyncio subprocess cleanup warnings after successful completion

Exact machine-local execution logs stay outside the repository-facing documentation surface.
