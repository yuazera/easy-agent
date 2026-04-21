from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import agent_runtime.public_eval as public_eval_module
from agent_config.app import AppConfig
from agent_runtime.public_eval import PublicEvalRecord, run_public_eval_suite
from agent_runtime.public_eval_simple_evals import load_simple_eval_cases


def test_load_simple_eval_cases_from_local_paths(tmp_path: Path) -> None:
    browsecomp_path = tmp_path / 'browsecomp.json'
    simpleqa_path = tmp_path / 'simpleqa.json'
    browsecomp_path.write_text(
        json.dumps(
            {
                'cases': [
                    {
                        'id': 'browse_1',
                        'question': 'Where is the official MCP spec?',
                        'answer': 'modelcontextprotocol.io',
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    simpleqa_path.write_text(
        json.dumps(
            {
                'cases': [
                    {
                        'id': 'simple_1',
                        'question': 'What language is this repository written in?',
                        'answer': 'Python',
                        'accepted_answers': ['python'],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    config = AppConfig.model_validate(
        {
            'graph': {'entrypoint': 'coordinator', 'agents': [{'name': 'coordinator'}]},
            'evaluation': {
                'public_eval': {
                    'profile': 'simple_evals_subset',
                    'simple_evals': {
                        'browsecomp_path': str(browsecomp_path),
                        'simpleqa_path': str(simpleqa_path),
                    },
                }
            },
        }
    )

    browsecomp_cases, simpleqa_cases = load_simple_eval_cases(config)

    assert browsecomp_cases[0]['id'] == 'browse_1'
    assert browsecomp_cases[0]['expected_answer'] == 'modelcontextprotocol.io'
    assert simpleqa_cases[0]['id'] == 'simple_1'
    assert simpleqa_cases[0]['expected_answer_aliases'][0] == 'Python'


def test_run_public_eval_suite_supports_simple_evals_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    browsecomp_path = tmp_path / 'browsecomp.json'
    simpleqa_path = tmp_path / 'simpleqa.json'
    browsecomp_path.write_text(
        json.dumps({'cases': [{'id': 'browse_1', 'question': 'Q1', 'answer': 'A1'}]}, ensure_ascii=False),
        encoding='utf-8',
    )
    simpleqa_path.write_text(
        json.dumps({'cases': [{'id': 'simple_1', 'question': 'Q2', 'answer': 'A2'}]}, ensure_ascii=False),
        encoding='utf-8',
    )
    config = yaml.safe_load(Path('easy-agent.yml').read_text(encoding='utf-8'))
    public_eval = config.setdefault('evaluation', {}).setdefault('public_eval', {})
    public_eval['profile'] = 'simple_evals_subset'
    public_eval.setdefault('official_dataset', {})['checkpoint_path'] = str(tmp_path / 'progress.json')
    public_eval['official_dataset']['resume'] = False
    public_eval.setdefault('simple_evals', {})['browsecomp_path'] = str(browsecomp_path)
    public_eval['simple_evals']['simpleqa_path'] = str(simpleqa_path)
    public_eval['simple_evals']['browsecomp_source_url'] = None
    public_eval['simple_evals']['simpleqa_source_url'] = None
    config_path = tmp_path / 'easy-agent.simple-evals.yml'
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')

    async def fake_run_simple_eval_case(
        _base_config: AppConfig,
        case: dict[str, object],
        *,
        suite: str,
    ) -> PublicEvalRecord:
        return PublicEvalRecord(
            suite=suite,
            case_id=str(case['id']),
            success=True,
            duration_seconds=0.01,
            tool_name_match=1.0,
            argument_match=1.0,
            expected_call_count=0,
            actual_call_count=0,
            result_summary='ok',
            answer_match=1.0,
        )

    monkeypatch.setattr(public_eval_module, '_run_simple_eval_case', fake_run_simple_eval_case)
    monkeypatch.setattr(public_eval_module, '_provider_live_matrix', lambda _base_config: {})
    monkeypatch.setattr(public_eval_module, '_provider_schema_matrix', lambda _matrix: {})

    report = run_public_eval_suite(config_path, profile='simple_evals_subset')

    assert report['profile'] == 'simple_evals_subset'
    assert report['scope'] == 'simple_evals'
    assert report['case_counts']['browsecomp'] == 1
    assert report['case_counts']['simpleqa'] == 1
    assert report['summary']['browsecomp']['pass_rate'] == 1.0
    assert report['summary']['simpleqa']['pass_rate'] == 1.0
    assert report['summary']['overall']['simple_evals_pass_rate'] == 1.0

