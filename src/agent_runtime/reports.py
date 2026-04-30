from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, cast

from agent_runtime.runtime import build_runtime


def read_json_report(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding='utf-8')))


def score(successes: int, runs: int) -> float | None:
    if runs <= 0:
        return None
    return round(successes / runs * 100, 4)


def summarize_benchmark_report(path: Path) -> dict[str, Any]:
    report = read_json_report(path)
    if report is None:
        return {'status': 'missing', 'path': str(path), 'score': None, 'summary': 'report not found'}
    raw_summary = report.get('summary')
    summary = cast(dict[str, Any], raw_summary) if isinstance(raw_summary, dict) else {}
    runs = sum(int(item.get('runs') or 0) for item in summary.values() if isinstance(item, dict))
    successes = sum(int(item.get('successes') or 0) for item in summary.values() if isinstance(item, dict))
    failures = sum(int(item.get('failures') or 0) for item in summary.values() if isinstance(item, dict))
    return {
        'status': 'available',
        'path': str(path),
        'score': score(successes, runs),
        'summary': f'{successes}/{runs} succeeded, {failures} failed',
        'runs': runs,
        'successes': successes,
        'failures': failures,
    }


def summarize_public_eval_report(path: Path) -> dict[str, Any]:
    report = read_json_report(path)
    if report is None:
        return {'status': 'missing', 'path': str(path), 'score': None, 'summary': 'report not found'}
    raw_summary = report.get('summary')
    summary = cast(dict[str, Any], raw_summary) if isinstance(raw_summary, dict) else {}
    raw_overall = summary.get('overall')
    overall = cast(dict[str, Any], raw_overall) if isinstance(raw_overall, dict) else {}
    score_value = overall.get('bfcl_subcategory_accuracy')
    if score_value is None:
        score_value = overall.get('bfcl_case_pass_rate')
    score_value = round(float(score_value) * 100, 4) if isinstance(score_value, int | float) else None
    raw_case_counts = report.get('case_counts')
    case_counts = cast(dict[str, Any], raw_case_counts) if isinstance(raw_case_counts, dict) else {}
    completed = case_counts.get('completed_records')
    return {
        'status': 'available',
        'path': str(path),
        'score': score_value,
        'summary': f"profile={report.get('profile', '-')}, completed={completed or '-'}",
        'profile': report.get('profile'),
        'completed_records': completed,
    }


def summarize_real_network_report(path: Path) -> dict[str, Any]:
    report = read_json_report(path)
    if report is None:
        return {'status': 'missing', 'path': str(path), 'score': None, 'summary': 'report not found'}
    raw_summary = report.get('summary')
    summary = cast(dict[str, Any], raw_summary) if isinstance(raw_summary, dict) else {}
    runs = int(summary.get('runs') or 0)
    passed = int(summary.get('passed') or 0)
    failed = int(summary.get('failed') or 0)
    skipped = int(summary.get('skipped') or 0)
    return {
        'status': 'available',
        'path': str(path),
        'score': score(passed, runs),
        'summary': f'{passed}/{runs} passed, {failed} failed, {skipped} skipped',
        'generated_at': report.get('generated_at'),
        'runs': runs,
        'passed': passed,
        'failed': failed,
        'skipped': skipped,
    }


def summarize_recent_runs(config: Path, limit: int) -> dict[str, Any]:
    if not config.is_file():
        return {'status': 'missing_config', 'config': str(config), 'summary': {}}
    try:
        runtime = build_runtime(config)
    except Exception as exc:
        return {'status': 'unavailable', 'config': str(config), 'error': str(exc), 'summary': {}}
    try:
        runs = runtime.store.list_runs(limit=limit)
        by_status: dict[str, int] = {}
        for run in runs:
            status = str(run.get('status') or 'unknown')
            by_status[status] = by_status.get(status, 0) + 1
        return {
            'status': 'available',
            'config': str(config),
            'summary': {'total': len(runs), 'by_status': by_status},
            'latest_run_id': str(runs[0]['run_id']) if runs else None,
        }
    finally:
        import asyncio

        asyncio.run(runtime.aclose())


def latest_report_payload(
    config: Path,
    *,
    benchmark_report: Path = Path('.easy-agent/benchmark-report.json'),
    public_eval_report: Path = Path('.easy-agent/public-eval-report.json'),
    real_network_report: Path = Path('.easy-agent/real-network-report.json'),
    run_limit: int = 50,
) -> dict[str, Any]:
    return {
        'reports': {
            'benchmark': summarize_benchmark_report(benchmark_report),
            'public_eval': summarize_public_eval_report(public_eval_report),
            'real_network': summarize_real_network_report(real_network_report),
        },
        'runs': summarize_recent_runs(config, run_limit),
    }


def build_cost_report(config: Path, *, run_limit: int = 100) -> dict[str, Any]:
    if not config.is_file():
        return {'status': 'missing_config', 'config': str(config), 'runs': [], 'summary': {}}
    try:
        runtime = build_runtime(config)
    except Exception as exc:
        return {'status': 'unavailable', 'config': str(config), 'error': str(exc), 'runs': [], 'summary': {}}
    try:
        runs = runtime.store.list_runs(limit=run_limit)
        rows: list[dict[str, Any]] = []
        totals = {
            'runs': len(runs),
            'failed': 0,
            'tool_spans': 0,
            'mcp_spans': 0,
            'model_spans': 0,
            'retry_count': 0,
            'duration_seconds': 0.0,
        }
        failure_layers: dict[str, int] = {}
        for run in runs:
            run_id = str(run['run_id'])
            tree = runtime.store.load_trace_tree(run_id)
            span_items = tree.get('spans')
            spans: list[Any] = span_items if isinstance(span_items, list) else []
            kinds: dict[str, int] = {}
            duration = 0.0
            retry_count = 0
            for raw_span in spans:
                span = raw_span if isinstance(raw_span, dict) else {}
                kind = str(span.get('kind') or 'unknown')
                kinds[kind] = kinds.get(kind, 0) + 1
                retry_count += int(span.get('retry_count') or 0)
                raw_duration = span.get('duration_seconds')
                if isinstance(raw_duration, int | float):
                    duration += float(raw_duration)
            status = str(run.get('status') or 'unknown')
            if status == 'failed':
                totals['failed'] += 1
                layer = _cost_failure_layer(spans)
                failure_layers[layer] = failure_layers.get(layer, 0) + 1
            totals['tool_spans'] += kinds.get('tool', 0)
            totals['mcp_spans'] += kinds.get('mcp', 0)
            totals['model_spans'] += kinds.get('model', 0)
            totals['retry_count'] += retry_count
            totals['duration_seconds'] = round(float(totals['duration_seconds']) + duration, 4)
            rows.append(
                {
                    'run_id': run_id,
                    'status': status,
                    'run_kind': run.get('run_kind'),
                    'span_count': len(spans),
                    'kinds': kinds,
                    'retry_count': retry_count,
                    'duration_seconds': round(duration, 4),
                    'estimated_cost_usd': None,
                    'cost_note': 'token usage is not available in stored traces; cost is best-effort telemetry only',
                }
            )
        return {
            'status': 'available',
            'config': str(config),
            'summary': {**totals, 'failure_layers': failure_layers},
            'runs': rows,
        }
    finally:
        import asyncio

        asyncio.run(runtime.aclose())


def cost_report_html(payload: dict[str, Any]) -> str:
    raw_runs = payload.get('runs')
    runs: list[Any] = raw_runs if isinstance(raw_runs, list) else []
    cards = []
    summary = payload.get('summary') if isinstance(payload.get('summary'), dict) else {}
    cards.append(
        '<section class="card">'
        '<h2>summary</h2>'
        f'<pre>{escape(json.dumps(summary, ensure_ascii=False, indent=2, default=str))}</pre>'
        '</section>'
    )
    for item_raw in runs[:12]:
        item = cast(dict[str, Any], item_raw) if isinstance(item_raw, dict) else {}
        cards.append(
            '<section class="card">'
            f'<h2>{escape(str(item.get("run_id") or "-"))}</h2>'
            f'<div class="status">{escape(str(item.get("status") or "unknown"))}</div>'
            f'<p>spans={escape(str(item.get("span_count") or 0))}, retries={escape(str(item.get("retry_count") or 0))}, seconds={escape(str(item.get("duration_seconds") or 0))}</p>'
            f'<pre>{escape(json.dumps(item, ensure_ascii=False, indent=2, default=str))}</pre>'
            '</section>'
        )
    return _report_shell('easy-agent cost and reliability report', 'Best-effort local run telemetry for cost, retries, tool use, and failure classes.', ''.join(cards), payload)


def _cost_failure_layer(spans: list[Any]) -> str:
    for raw_span in spans:
        span = raw_span if isinstance(raw_span, dict) else {}
        if str(span.get('status') or '') == 'failed':
            return str(span.get('kind') or 'unknown')
    return 'unknown'


def latest_report_html(payload: dict[str, Any]) -> str:
    reports_raw = payload.get('reports')
    reports = cast(dict[str, Any], reports_raw) if isinstance(reports_raw, dict) else {}
    runs_raw = payload.get('runs')
    runs = cast(dict[str, Any], runs_raw) if isinstance(runs_raw, dict) else {}
    cards: list[str] = []
    for name, item_raw in reports.items():
        item = cast(dict[str, Any], item_raw) if isinstance(item_raw, dict) else {}
        cards.append(
            '<section class="card">'
            f'<h2>{escape(str(name))}</h2>'
            f'<div class="status">{escape(str(item.get("status", "unknown")))}</div>'
            f'<p class="score">{escape(str(item.get("score") if item.get("score") is not None else "-"))}</p>'
            f'<p>{escape(str(item.get("summary") or "-"))}</p>'
            f'<pre>{escape(json.dumps(item, ensure_ascii=False, indent=2, default=str))}</pre>'
            '</section>'
        )
    cards.append(
        '<section class="card">'
        '<h2>runs</h2>'
        f'<div class="status">{escape(str(runs.get("status", "unknown")))}</div>'
        f'<p>{escape(json.dumps(runs.get("summary", {}), ensure_ascii=False, default=str))}</p>'
        f'<pre>{escape(json.dumps(runs, ensure_ascii=False, indent=2, default=str))}</pre>'
        '</section>'
    )
    return _report_shell('easy-agent latest report', 'Local benchmark, public-eval, real-network, and recent-run evidence.', ''.join(cards), payload)


def build_report_trend(history: Path, limit: int = 10) -> dict[str, Any]:
    surfaces = {
        'benchmark': ('benchmark-report*.json', summarize_benchmark_report),
        'public_eval': ('public-eval-report*.json', summarize_public_eval_report),
        'real_network': ('real-network-report*.json', summarize_real_network_report),
    }
    payload: dict[str, Any] = {'history': str(history), 'limit': limit, 'surfaces': {}}
    for name, (pattern, summarizer) in surfaces.items():
        paths = sorted(history.glob(pattern), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
        points = []
        for path in paths[:limit]:
            point = summarizer(path)
            point['modified_at_epoch'] = path.stat().st_mtime
            points.append(point)
        latest = points[0] if points else {'status': 'missing', 'score': None}
        previous = points[1] if len(points) > 1 else None
        latest_score = latest.get('score') if isinstance(latest, dict) else None
        previous_score = previous.get('score') if isinstance(previous, dict) else None
        delta = (
            round(float(latest_score) - float(previous_score), 4)
            if isinstance(latest_score, int | float) and isinstance(previous_score, int | float)
            else None
        )
        payload['surfaces'][name] = {
            'latest': latest,
            'previous': previous,
            'score_delta': delta,
            'points': points,
        }
    return payload


def report_trend_html(payload: dict[str, Any]) -> str:
    raw_surfaces = payload.get('surfaces')
    surfaces = cast(dict[str, Any], raw_surfaces) if isinstance(raw_surfaces, dict) else {}
    cards = []
    for name, item_raw in surfaces.items():
        item = cast(dict[str, Any], item_raw) if isinstance(item_raw, dict) else {}
        latest = cast(dict[str, Any], item.get('latest')) if isinstance(item.get('latest'), dict) else {}
        cards.append(
            '<section class="card">'
            f'<h2>{escape(str(name))}</h2>'
            f'<div class="status">delta {escape(str(item.get("score_delta") if item.get("score_delta") is not None else "-"))}</div>'
            f'<p class="score">{escape(str(latest.get("score") if latest.get("score") is not None else "-"))}</p>'
            f'<p>{escape(str(latest.get("summary") or latest.get("status") or "-"))}</p>'
            f'<pre>{escape(json.dumps(item.get("points", []), ensure_ascii=False, indent=2, default=str))}</pre>'
            '</section>'
        )
    return _report_shell('easy-agent report trend', 'Score and status movement across local report artifacts.', ''.join(cards), payload)


def _report_shell(title: str, lead: str, body: str, payload: dict[str, Any]) -> str:
    raw_json = escape(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #1d2430; }}
    main {{ width: min(1120px, calc(100% - 32px)); margin: 0 auto; padding: 32px 0 48px; }}
    h1 {{ margin: 0 0 6px; font-size: 28px; line-height: 1.2; }}
    .lead {{ margin: 0 0 24px; color: #526070; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }}
    .card {{ background: #ffffff; border: 1px solid #d8dee7; border-radius: 8px; padding: 16px; box-shadow: 0 1px 2px rgba(20, 30, 45, 0.06); }}
    .card h2 {{ margin: 0 0 10px; font-size: 16px; }}
    .status {{ display: inline-flex; padding: 3px 8px; border-radius: 999px; background: #e7f0ff; color: #164f9f; font-size: 12px; font-weight: 700; }}
    .score {{ margin: 14px 0 8px; font-size: 28px; font-weight: 750; }}
    pre {{ overflow: auto; max-height: 280px; margin: 12px 0 0; padding: 12px; border-radius: 6px; background: #101827; color: #d8e3f8; font-size: 12px; }}
    details {{ margin-top: 18px; }}
    summary {{ cursor: pointer; font-weight: 700; }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #101419; color: #e7ecf3; }}
      .lead {{ color: #a7b3c4; }}
      .card {{ background: #171d25; border-color: #2a3340; box-shadow: none; }}
      .status {{ background: #17345c; color: #9fc6ff; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    <p class="lead">{escape(lead)}</p>
    <div class="grid">{body}</div>
    <details>
      <summary>Raw JSON</summary>
      <pre>{raw_json}</pre>
    </details>
  </main>
</body>
</html>
"""
