from __future__ import annotations

from typing import Any


def trace_tree_to_otel_json(payload: dict[str, Any]) -> dict[str, Any]:
    run = dict(payload.get('run') or {})
    spans = payload.get('spans')
    span_items = spans if isinstance(spans, list) else []
    run_id = str(run.get('run_id') or 'unknown')
    otel_spans: list[dict[str, Any]] = []
    for item in span_items:
        if not isinstance(item, dict):
            continue
        attributes = dict(item.get('attributes') or {})
        attributes.update(
            {
                'easy_agent.run_id': run_id,
                'easy_agent.kind': item.get('kind'),
                'easy_agent.retry_count': item.get('retry_count'),
                'easy_agent.checkpoint_id': item.get('checkpoint_id'),
                'easy_agent.input_hash': item.get('input_hash'),
                'easy_agent.output_hash': item.get('output_hash'),
            }
        )
        otel_spans.append(
            {
                'trace_id': run_id,
                'span_id': str(item.get('span_id') or ''),
                'parent_span_id': item.get('parent_span_id'),
                'name': str(item.get('name') or item.get('span_id') or 'span'),
                'kind': str(item.get('kind') or 'internal'),
                'status': {'code': str(item.get('status') or 'unknown')},
                'start_time': item.get('started_at'),
                'end_time': item.get('ended_at'),
                'attributes': {key: value for key, value in attributes.items() if value is not None},
            }
        )
    return {
        'experimental': True,
        'schema_url': 'https://opentelemetry.io/docs/specs/semconv/gen-ai/',
        'source': 'easy-agent trace tree',
        'run': run,
        'resource_spans': [
            {
                'resource': {
                    'attributes': {
                        'service.name': 'easy-agent',
                        'easy_agent.run_id': run_id,
                        'easy_agent.run_kind': run.get('run_kind'),
                    }
                },
                'scope_spans': [
                    {
                        'scope': {'name': 'easy-agent.runtime', 'version': 'experimental'},
                        'spans': otel_spans,
                    }
                ],
            }
        ],
    }
