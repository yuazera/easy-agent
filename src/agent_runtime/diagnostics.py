from __future__ import annotations

import json
from typing import Any, Protocol

from agent_common.models import RunStatus


class DiagnosticStore(Protocol):
    def load_run_summary(self, run_id: str) -> dict[str, Any]: ...
    def load_trace(self, run_id: str) -> dict[str, Any]: ...


def explain_run(store: DiagnosticStore, run_id: str) -> dict[str, Any]:
    summary = store.load_run_summary(run_id)
    trace = store.load_trace(run_id)
    events = [dict(item) for item in trace.get('events', []) if isinstance(item, dict)]
    event_kinds = [str(item.get('kind') or '') for item in events]
    text = json.dumps({'summary': summary, 'events': events}, ensure_ascii=False, default=str)
    status = str(summary.get('status') or trace.get('status') or '')

    layer, headline, actions = _classify(status, event_kinds, text)
    evidence = _evidence(summary, events, text)
    return {
        'run_id': run_id,
        'status': status,
        'likely_layer': layer,
        'headline': headline,
        'evidence': evidence,
        'recommended_actions': actions,
        'counts': {
            'events': int(summary.get('event_count') or len(events)),
            'nodes': int(summary.get('node_count') or len(trace.get('nodes', []))),
            'checkpoints': int(summary.get('checkpoint_count') or len(trace.get('checkpoints', []))),
            'human_requests': int(summary.get('human_request_count') or len(trace.get('human_requests', []))),
        },
    }


def _classify(status: str, event_kinds: list[str], text: str) -> tuple[str, str, list[str]]:
    if status == RunStatus.SUCCEEDED.value:
        if any('retry' in kind or 'repair' in kind for kind in event_kinds):
            return (
                'runtime_recovery',
                'Run succeeded after a retry or repair path.',
                ['Inspect trace spans to confirm the retry path is expected before using the run as a golden example.'],
            )
        return ('success', 'Run completed successfully.', ['Use traces export --tree when you need detailed timing or tool-call context.'])
    if status == RunStatus.WAITING_APPROVAL.value:
        return (
            'human_approval',
            'Run is waiting for a human approval request.',
            ['Use approvals list/show, then approve or reject the pending request before resuming the run.'],
        )
    if status == RunStatus.INTERRUPTED.value:
        return (
            'human_interrupt',
            'Run was interrupted at a safe point.',
            ['Inspect checkpoints and resume or fork from the latest safe checkpoint when ready.'],
        )
    if 'Missing API key environment variable' in text:
        return (
            'model_provider',
            'The configured model provider is missing its API key environment variable.',
            ['Set the configured api_key_env value, or rerun the workflow with the mock provider for offline validation.'],
        )
    if any(kind == 'tool_validation_failed' for kind in event_kinds):
        return (
            'tool_validation',
            'A tool call did not satisfy the registered input schema.',
            ['Inspect the tool_validation_failed event and tighten the tool prompt or schema before rerunning.'],
        )
    if 'guardrail' in text and '"outcome": "block"' in text:
        return (
            'guardrail',
            'A guardrail blocked tool input or final output.',
            ['Inspect guardrail events and decide whether the input, tool arguments, or policy should change.'],
        )
    if any(kind == 'tool_call_failed' for kind in event_kinds):
        return (
            'tool_runtime',
            'A tool raised an exception during execution.',
            ['Inspect the failed tool event and reproduce the tool with the recorded normalized arguments.'],
        )
    if 'MCP' in text or 'mcp' in text:
        return (
            'mcp',
            'The failure appears related to MCP transport, catalog, or tool execution.',
            ['Run mcp list/resources/prompts checks for the configured server and verify roots, auth, and transport startup.'],
        )
    if 'max_iterations' in text or 'exceeded max_iterations' in text:
        return (
            'agent_loop',
            'The agent exceeded its iteration budget.',
            ['Tighten the agent prompt/tool contract, block duplicate tool loops, or raise max_iterations only after reviewing trace output.'],
        )
    if 'Event loop is closed' in text or 'I/O operation on closed pipe' in text:
        return (
            'cleanup_warning',
            'The run encountered a known Windows asyncio subprocess cleanup warning.',
            ['Treat this as cleanup debt when the test result is otherwise green; inspect subprocess teardown if it starts failing the suite.'],
        )
    return (
        'runtime',
        'Run failed, but no specialized classifier matched the stored trace.',
        ['Export the trace tree and inspect the latest run_failed, node failure, or tool event.'],
    )


def _evidence(summary: dict[str, Any], events: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    output_payload = summary.get('output_payload')
    if output_payload:
        evidence.append({'source': 'run.output_payload', 'value': output_payload})
    for event in events[-8:]:
        kind = str(event.get('kind') or '')
        if kind.endswith('failed') or kind in {'tool_validation_failed', 'run_waiting_approval', 'run_interrupted'}:
            evidence.append({'source': f"event:{kind}", 'value': event.get('payload') or {}})
    if 'Event loop is closed' in text:
        evidence.append({'source': 'known_warning', 'value': 'Event loop is closed'})
    if 'I/O operation on closed pipe' in text:
        evidence.append({'source': 'known_warning', 'value': 'I/O operation on closed pipe'})
    return evidence[:6]
