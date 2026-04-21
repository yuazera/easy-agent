from __future__ import annotations

from agent_common.models import RunContext
from agent_config.app import PublicEvalWebSearchConfig
from agent_integrations.official_source_search import (
    fetch_contents,
    normalize_num_results,
    search,
    shape_query,
)


def run(arguments: dict[str, object], context: RunContext) -> dict[str, object]:
    del context
    raw_query = str(arguments.get('query') or '')
    preferred_domains = [str(item) for item in (arguments.get('preferred_domains') or []) if str(item).strip()]
    mode = str(arguments.get('mode') or 'preferred_first').strip().casefold()
    config = PublicEvalWebSearchConfig(
        source_policy=mode if mode in {'general', 'preferred_first', 'preferred_only'} else 'preferred_first',
        preferred_domains=preferred_domains,
    )
    query = shape_query(raw_query, prefer_official=bool(preferred_domains))
    report = search(
        query=query,
        num_results=normalize_num_results(arguments.get('num_results'), default=5, maximum=10),
        config=config,
        preferred_domains=preferred_domains,
        source_policy=config.source_policy,
    )
    if not bool(arguments.get('fetch_contents')):
        return report
    results = list(report.get('results', []))
    if not results:
        return {**report, 'contents': None}
    try:
        result_index = max(0, int(arguments.get('result_index') or 0))
    except (TypeError, ValueError):
        result_index = 0
    selected = results[min(result_index, len(results) - 1)]
    contents = fetch_contents(
        str(selected.get('link') or ''),
        config=config,
        mode=str(arguments.get('content_mode') or 'truncate'),
    )
    return {**report, 'contents': contents}
