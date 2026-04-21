from __future__ import annotations

import os
import re
from typing import Any, cast
from urllib.parse import urlparse

import httpx

from agent_config.app import PublicEvalWebSearchConfig

SEARCH_PREFIX_PATTERN = re.compile(
    r'^(search(\s+the)?\s+web(\s+for)?|web\s+search(\s+for)?|look\s+up|find)\s*[:,-]?\s*',
    re.IGNORECASE,
)
TRAILING_TITLE_QUESTION_PATTERN = re.compile(
    r'[\s,;:-]*(what\s+is\s+the\s+(exact\s+)?page\s+title|what\s+is\s+its\s+title|return\s+the\s+exact\s+page\s+title)\??\s*$',
    re.IGNORECASE,
)
QUOTE_STRIP = "\"'` "
MAX_QUERY_LENGTH = 180
SUPPORTED_CONTENT_MODES = {'truncate', 'raw', 'markdown'}


def site_name(url: str, fallback: str = 'unknown') -> str:
    parsed = urlparse(url)
    return parsed.netloc or fallback


def normalize_contents_mode(value: Any) -> str:
    mode = str(value or 'truncate').strip().casefold()
    return mode if mode in SUPPORTED_CONTENT_MODES else 'truncate'


def shape_query(
    raw_query: str,
    *,
    fallback_prompt: str = '',
    prefer_official: bool = False,
    max_length: int = MAX_QUERY_LENGTH,
) -> str:
    prompt = fallback_prompt.strip()
    query = raw_query.strip() or prompt
    query = SEARCH_PREFIX_PATTERN.sub('', query, count=1)
    query = TRAILING_TITLE_QUESTION_PATTERN.sub('', query)
    query = re.sub(r'\s+', ' ', query).strip(QUOTE_STRIP)
    query = query.rstrip(' .,:;!?')
    if prefer_official and 'official' not in query.casefold():
        query = f'official {query}'.strip()
    if len(query) <= max_length:
        return query
    trimmed = query[:max_length].rsplit(' ', 1)[0].strip()
    return trimmed or query[:max_length].strip()


def normalize_num_results(value: Any, *, default: int = 5, maximum: int = 10) -> int:
    try:
        number = int(value or default)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, maximum))


def normalize_search_results(payload: dict[str, Any], *, num_results: int) -> list[dict[str, Any]]:
    raw_results = payload.get('organic_results', [])
    if not isinstance(raw_results, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_results[:num_results], start=1):
        if not isinstance(item, dict):
            continue
        link = str(item.get('link') or item.get('url') or '').strip()
        normalized.append(
            {
                'position': int(item.get('position') or index),
                'title': str(item.get('title') or item.get('name') or '').strip(),
                'link': link,
                'source': str(item.get('source') or item.get('displayed_link') or site_name(link)),
                'snippet': str(item.get('text') or item.get('snippet') or '').strip(),
            }
        )
    return normalized


def source_domain(url: str) -> str:
    return urlparse(url).netloc.casefold().lstrip('.')


def source_matches(url: str, preferred_domains: list[str]) -> bool:
    domain = source_domain(url)
    normalized = [item.strip().casefold().lstrip('.') for item in preferred_domains if item.strip()]
    return any(domain == item or domain.endswith(f'.{item}') for item in normalized)


def apply_source_policy(
    results: list[dict[str, Any]],
    *,
    source_policy: str,
    preferred_domains: list[str],
) -> list[dict[str, Any]]:
    if not preferred_domains or source_policy == 'general':
        return list(results)
    preferred = [item for item in results if source_matches(str(item.get('link') or ''), preferred_domains)]
    if source_policy == 'preferred_only':
        return preferred
    others = [item for item in results if item not in preferred]
    return preferred + others


def serpapi_query_params(
    *,
    query: str,
    num_results: int,
    config: PublicEvalWebSearchConfig,
) -> dict[str, Any]:
    return {
        'q': query,
        'num': num_results,
        'engine': config.engine,
        'google_domain': config.google_domain,
        'hl': config.hl,
        'gl': config.gl,
    }


def search(
    *,
    query: str,
    num_results: int,
    config: PublicEvalWebSearchConfig,
    preferred_domains: list[str] | None = None,
    source_policy: str | None = None,
) -> dict[str, Any]:
    key = str(os.environ.get(config.api_key_env, '')).strip()
    if not key:
        raise RuntimeError(f'missing {config.api_key_env} for official source search')
    params = serpapi_query_params(query=query, num_results=num_results, config=config)
    response = httpx.get(
        config.endpoint_url,
        params={**params, 'api_key': key},
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()
    results = normalize_search_results(cast(dict[str, Any], response.json()), num_results=num_results)
    resolved_domains = preferred_domains if preferred_domains is not None else list(config.preferred_domains)
    resolved_policy = source_policy if source_policy is not None else config.source_policy
    ranked = apply_source_policy(results, source_policy=resolved_policy, preferred_domains=resolved_domains)
    return {
        'query': query,
        'results': ranked,
        'backend': 'serpapi',
        'source_policy': resolved_policy,
        'preferred_domains': resolved_domains,
    }


def strip_html_text(value: str) -> str:
    collapsed = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', value, flags=re.IGNORECASE | re.DOTALL)
    collapsed = re.sub(r'<[^>]+>', ' ', collapsed)
    collapsed = re.sub(r'\s+', ' ', collapsed)
    return collapsed.strip()


def html_to_markdown_like_text(value: str) -> str:
    text = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<\s*br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/?\s*p\s*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/?\s*div\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*h([1-6])\s*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/\s*h[1-6]\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*li\s*>', '\n- ', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/\s*li\s*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def fetch_contents(
    url: str,
    *,
    config: PublicEvalWebSearchConfig,
    mode: str = 'truncate',
) -> dict[str, Any]:
    normalized_mode = normalize_contents_mode(mode)
    response = httpx.get(url, timeout=config.timeout_seconds, follow_redirects=True)
    response.raise_for_status()
    body = response.text
    if normalized_mode == 'raw':
        text = body
    elif normalized_mode == 'markdown':
        text = html_to_markdown_like_text(body)
    else:
        text = strip_html_text(body)
        if len(text) > 4000:
            text = text[:4000].rstrip()
    return {'url': url, 'mode': normalized_mode, 'text': text}
