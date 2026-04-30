from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path
from typing import Any, Protocol

from agent_runtime.diagnostics import (
    build_fix_package,
    build_triage_package,
    fix_package_html,
    fix_package_markdown,
)


class BundleStore(Protocol):
    def load_run_summary(self, run_id: str) -> dict[str, Any]: ...
    def load_trace(self, run_id: str) -> dict[str, Any]: ...
    def load_trace_tree(self, run_id: str) -> dict[str, Any]: ...


def write_run_bundle(
    store: BundleStore,
    run_id: str,
    output_dir: Path,
    *,
    browser_payload: dict[str, Any] | None = None,
    artifact_limit: int = 50,
    copy_browser_artifacts: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise FileExistsError(f'Bundle output directory is not empty: {output_dir}')
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = store.load_run_summary(run_id)
    triage = build_triage_package(store, run_id)
    fix = build_fix_package(store, run_id)
    trace_tree = store.load_trace_tree(run_id)
    browser = browser_payload or {'count': 0, 'artifacts': []}

    _write_json(output_dir / 'run-summary.json', summary)
    _write_json(output_dir / 'triage.json', triage)
    _write_json(output_dir / 'trace-tree.json', trace_tree)
    _write_json(output_dir / 'browser-artifacts.json', browser)
    (output_dir / 'fix.md').write_text(fix_package_markdown(fix), encoding='utf-8')
    (output_dir / 'fix.html').write_text(fix_package_html(fix), encoding='utf-8')
    (output_dir / 'trace.html').write_text(_trace_html(trace_tree), encoding='utf-8')
    copied = _copy_browser_artifacts(browser, output_dir / 'browser-artifacts', limit=artifact_limit) if copy_browser_artifacts else []
    readme = _bundle_readme(run_id, summary, triage, copied)
    (output_dir / 'README.md').write_text(readme, encoding='utf-8')

    files = [
        'run-summary.json',
        'triage.json',
        'fix.md',
        'fix.html',
        'trace-tree.json',
        'trace.html',
        'browser-artifacts.json',
        'README.md',
    ]
    if copied:
        files.append('browser-artifacts/')
    return {
        'run_id': run_id,
        'mode': 'advice_only',
        'output_dir': str(output_dir),
        'files': files,
        'copied_browser_artifacts': copied,
        'selected_task_pack': triage.get('selected_task_pack'),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def _copy_browser_artifacts(browser: dict[str, Any], target: Path, *, limit: int) -> list[dict[str, Any]]:
    raw_items = browser.get('artifacts')
    items: list[Any] = raw_items if isinstance(raw_items, list) else []
    copied: list[dict[str, Any]] = []
    for item in items[: max(0, limit)]:
        if not isinstance(item, dict):
            continue
        source = Path(str(item.get('path') or ''))
        if not source.exists() or not source.is_file():
            continue
        relative = _safe_relative(str(item.get('relative_path') or source.name))
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(
            {
                'source': str(source),
                'relative_path': str(relative),
                'kind': item.get('kind') or 'other',
                'size_bytes': item.get('size_bytes') or destination.stat().st_size,
            }
        )
    return copied


def _safe_relative(value: str) -> Path:
    parts = [part for part in Path(value).parts if part not in {'', '.', '..'}]
    if not parts:
        return Path('artifact')
    return Path(*parts)


def _bundle_readme(run_id: str, summary: dict[str, Any], triage: dict[str, Any], copied: list[dict[str, Any]]) -> str:
    raw_commands = triage.get('next_commands')
    commands: list[Any] = raw_commands if isinstance(raw_commands, list) else []
    command_lines = '\n'.join(f'- `{item}`' for item in commands) or '- Review `triage.json` and `trace-tree.json`.'
    return '\n'.join(
        [
            f'# easy-agent run bundle: {run_id}',
            '',
            'This directory is an advice-only evidence package. It does not apply patches, rerun agents, or bypass approvals.',
            '',
            '## Contents',
            '',
            '- `run-summary.json`: stored run summary and counts.',
            '- `triage.json`: first-response triage and next commands.',
            '- `fix.md` / `fix.html`: shareable repair prompt and safety notes.',
            '- `trace-tree.json` / `trace.html`: structured runtime trace evidence.',
            '- `browser-artifacts.json`: browser artifact inventory.',
            '- `browser-artifacts/`: copied browser artifacts when available.',
            '',
            '## Run State',
            '',
            f"- Status: `{summary.get('status', 'unknown')}`",
            f"- Likely layer: `{triage.get('likely_layer', 'unknown')}`",
            f"- Selected task pack: `{triage.get('selected_task_pack', '-')}`",
            f"- Copied browser artifacts: `{len(copied)}`",
            '',
            '## Next Commands',
            '',
            command_lines,
            '',
        ]
    )


def _trace_html(payload: dict[str, Any]) -> str:
    raw_run = payload.get('run')
    run: dict[str, Any] = raw_run if isinstance(raw_run, dict) else {}
    raw_tree = payload.get('tree')
    tree: list[Any] = raw_tree if isinstance(raw_tree, list) else []
    rows = ''.join(_span_row(item if isinstance(item, dict) else {}) for item in tree)
    raw_json = escape(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>easy-agent trace bundle {escape(str(run.get('run_id') or ''))}</title>
  <style>
    :root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f7f5ef; color: #20242b; }}
    main {{ width: min(1080px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 42px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    table {{ width: 100%; border-collapse: collapse; background: #fffdfa; border: 1px solid #d8d0c2; border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #eee4d5; text-align: left; vertical-align: top; font-size: 13px; }}
    tr:last-child td {{ border-bottom: 0; }}
    pre {{ overflow: auto; padding: 12px; border-radius: 8px; background: #20242b; color: #f7f5ef; }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #151515; color: #f3efe5; }}
      table {{ background: #20201f; border-color: #38332a; }}
      th, td {{ border-color: #38332a; }}
      pre {{ background: #0f1115; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>easy-agent trace bundle</h1>
    <p>Run: <code>{escape(str(run.get('run_id') or '-'))}</code> Status: <code>{escape(str(run.get('status') or '-'))}</code></p>
    <table><thead><tr><th>Span</th><th>Kind</th><th>Status</th><th>Duration</th></tr></thead><tbody>{rows or '<tr><td colspan="4">No spans recorded.</td></tr>'}</tbody></table>
    <details>
      <summary>Raw trace JSON</summary>
      <pre>{raw_json}</pre>
    </details>
  </main>
</body>
</html>
"""


def _span_row(span: dict[str, Any]) -> str:
    return (
        '<tr>'
        f'<td>{escape(str(span.get("name") or span.get("span_id") or "-"))}</td>'
        f'<td>{escape(str(span.get("kind") or "-"))}</td>'
        f'<td>{escape(str(span.get("status") or "-"))}</td>'
        f'<td>{escape(str(span.get("duration_seconds") if span.get("duration_seconds") is not None else "-"))}</td>'
        '</tr>'
    )
