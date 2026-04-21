from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx

from agent_config.app import AppConfig, PublicEvalSimpleEvalsConfig


def _load_json_or_jsonl(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding='utf-8').strip()
    if not text:
        return {}
    if path.suffix.lower() == '.jsonl':
        return {'cases': [json.loads(line) for line in text.splitlines() if line.strip()]}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(payload, dict):
        return cast(dict[str, Any], payload)
    return {'cases': cast(list[dict[str, Any]], payload)}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _cache_payload(source_url: str, cache_path: Path) -> dict[str, Any]:
    if cache_path.is_file():
        return _load_json_or_jsonl(cache_path)
    response = httpx.get(source_url, timeout=30.0)
    response.raise_for_status()
    text = response.text
    if cache_path.suffix.lower() == '.jsonl':
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding='utf-8')
        return _load_json_or_jsonl(cache_path)
    try:
        payload = cast(dict[str, Any], response.json())
    except json.JSONDecodeError:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding='utf-8')
        return _load_json_or_jsonl(cache_path)
    _write_json(cache_path, payload)
    return payload


def _payload_cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ('cases', 'records', 'examples', 'items', 'questions'):
        value = payload.get(key)
        if isinstance(value, list):
            return [cast(dict[str, Any], item) for item in value if isinstance(item, dict)]
    if isinstance(payload.get('data'), list):
        return [cast(dict[str, Any], item) for item in payload['data'] if isinstance(item, dict)]
    return []


def _case_aliases(raw_case: dict[str, Any]) -> list[str]:
    aliases = raw_case.get('aliases') or raw_case.get('expected_answer_aliases') or raw_case.get('accepted_answers') or []
    if not isinstance(aliases, list):
        return []
    return [str(item).strip() for item in aliases if str(item).strip()]


def _case_prompt(raw_case: dict[str, Any]) -> str:
    for key in ('question', 'prompt', 'input', 'problem', 'task'):
        value = raw_case.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def _case_answer(raw_case: dict[str, Any]) -> str:
    for key in ('answer', 'expected_answer', 'target', 'ideal', 'reference_answer'):
        value = raw_case.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def _normalize_browsecomp_case(raw_case: dict[str, Any], *, index: int) -> dict[str, Any]:
    prompt = _case_prompt(raw_case)
    if not prompt:
        raise RuntimeError('browsecomp case is missing a question/prompt field')
    expected_answer = _case_answer(raw_case)
    return {
        'id': str(raw_case.get('id') or raw_case.get('case_id') or raw_case.get('question_id') or f'browsecomp_{index}'),
        'prompt': prompt,
        'expected_answer': expected_answer,
        'expected_answer_aliases': _case_aliases(raw_case),
        'source_url': raw_case.get('source_url') or raw_case.get('url'),
        'metadata': {
            'task_family': 'browsecomp',
            'source_title': raw_case.get('source_title'),
        },
    }


def _normalize_simpleqa_case(raw_case: dict[str, Any], *, index: int) -> dict[str, Any]:
    prompt = _case_prompt(raw_case)
    if not prompt:
        raise RuntimeError('simpleqa case is missing a question/prompt field')
    expected_answer = _case_answer(raw_case)
    aliases = _case_aliases(raw_case)
    if expected_answer and expected_answer not in aliases:
        aliases = [expected_answer, *aliases]
    return {
        'id': str(raw_case.get('id') or raw_case.get('case_id') or raw_case.get('question_id') or f'simpleqa_{index}'),
        'prompt': prompt,
        'expected_answer': expected_answer,
        'expected_answer_aliases': aliases,
        'source_url': raw_case.get('source_url') or raw_case.get('url'),
        'metadata': {
            'task_family': 'simpleqa',
            'topic': raw_case.get('topic') or raw_case.get('category'),
        },
    }


def _apply_case_filters(cases: list[dict[str, Any]], *, allowlist: list[str], max_cases: int | None) -> list[dict[str, Any]]:
    selected = list(cases)
    if allowlist:
        allowed = {item.strip() for item in allowlist if item.strip()}
        selected = [case for case in selected if str(case.get('id') or '').strip() in allowed]
    if max_cases is not None:
        selected = selected[:max(0, max_cases)]
    return selected


def _load_payload(
    *,
    path_value: str | None,
    source_url: str | None,
    cache_path: Path,
) -> dict[str, Any]:
    if path_value:
        path = Path(path_value)
        if not path.is_file():
            raise RuntimeError(f'missing simple eval dataset at {path}')
        return _load_json_or_jsonl(path)
    if source_url:
        return _cache_payload(source_url, cache_path)
    return {}


def load_simple_eval_cases(base_config: AppConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config: PublicEvalSimpleEvalsConfig = base_config.evaluation.public_eval.simple_evals
    cache_dir = Path(config.cache_dir)
    browsecomp_payload = _load_payload(
        path_value=config.browsecomp_path,
        source_url=config.browsecomp_source_url,
        cache_path=cache_dir / 'browsecomp.json',
    )
    simpleqa_payload = _load_payload(
        path_value=config.simpleqa_path,
        source_url=config.simpleqa_source_url,
        cache_path=cache_dir / 'simpleqa.json',
    )
    browsecomp_cases = [
        _normalize_browsecomp_case(case, index=index)
        for index, case in enumerate(_payload_cases(browsecomp_payload))
    ]
    simpleqa_cases = [
        _normalize_simpleqa_case(case, index=index)
        for index, case in enumerate(_payload_cases(simpleqa_payload))
    ]
    browsecomp_cases = _apply_case_filters(
        browsecomp_cases,
        allowlist=list(config.browsecomp_case_allowlist),
        max_cases=config.browsecomp_max_cases,
    )
    simpleqa_cases = _apply_case_filters(
        simpleqa_cases,
        allowlist=list(config.simpleqa_case_allowlist),
        max_cases=config.simpleqa_max_cases,
    )
    return browsecomp_cases, simpleqa_cases

