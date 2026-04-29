from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskPack:
    name: str
    description: str
    recommended_scenario: str
    prompt_template: str
    acceptance_criteria: list[str]


_TASK_PACKS: dict[str, TaskPack] = {
    'repo-review': TaskPack(
        name='repo-review',
        description='Review a repository for correctness, risks, and missing tests.',
        recommended_scenario='coding-agent',
        prompt_template=(
            'Review the current repository. Focus on bugs, regressions, risky assumptions, '
            'missing tests, and the smallest actionable fix list.\n\nContext:\n{context}'
        ),
        acceptance_criteria=[
            'Findings are ordered by severity.',
            'Each finding names concrete files or surfaces when evidence exists.',
            'The final answer separates open questions from confirmed issues.',
        ],
    ),
    'bug-fix': TaskPack(
        name='bug-fix',
        description='Investigate and fix a reported bug with verification.',
        recommended_scenario='coding-agent',
        prompt_template=(
            'Investigate and fix this bug. Keep the change scoped, add or update tests, '
            'and summarize the verification.\n\nBug report:\n{context}'
        ),
        acceptance_criteria=[
            'Root cause is stated before the fix summary.',
            'Tests cover the repaired behavior.',
            'Unrelated changes are avoided.',
        ],
    ),
    'docs-refresh': TaskPack(
        name='docs-refresh',
        description='Refresh documentation after a behavior or CLI change.',
        recommended_scenario='document-agent',
        prompt_template=(
            'Refresh the documentation for this change. Keep English and Chinese docs in sync, '
            'avoid local machine paths, and update reference docs where needed.\n\nChange:\n{context}'
        ),
        acceptance_criteria=[
            'Bilingual README files remain aligned.',
            'Reference docs include command examples and constraints.',
            'No secrets, local usernames, or absolute workspace paths are introduced.',
        ],
    ),
    'release-check': TaskPack(
        name='release-check',
        description='Run a release-readiness pass over tests, docs, and changelog state.',
        recommended_scenario='release-agent',
        prompt_template=(
            'Run a release readiness check. Inspect docs, changelog, verification evidence, '
            'and remaining risks before recommending release or hold.\n\nRelease context:\n{context}'
        ),
        acceptance_criteria=[
            'Verification commands are listed.',
            'Release blockers are separated from follow-up work.',
            'Changelog and public docs are checked for drift.',
        ],
    ),
    'data-summary': TaskPack(
        name='data-summary',
        description='Summarize a data file, metrics snapshot, or report with assumptions.',
        recommended_scenario='data-agent',
        prompt_template=(
            'Summarize the data or metrics below. Separate observed facts, assumptions, '
            'and recommended next steps.\n\nData context:\n{context}'
        ),
        acceptance_criteria=[
            'Findings are evidence-backed.',
            'Assumptions and missing fields are explicit.',
            'Recommendations are prioritized.',
        ],
    ),
    'federation-loopback-demo': TaskPack(
        name='federation-loopback-demo',
        description='Validate local federation surfaces and explain the resulting evidence.',
        recommended_scenario='federation-loopback',
        prompt_template=(
            'Validate the local federation loopback flow and explain the evidence to inspect. '
            'Cover agent card, task send, stream or polling, resubscribe, and callback safety.\n\nContext:\n{context}'
        ),
        acceptance_criteria=[
            'Agent card and task state surfaces are named.',
            'Push or polling behavior is explained.',
            'Security checks are called out.',
        ],
    ),
}


def list_task_packs() -> list[TaskPack]:
    return list(_TASK_PACKS.values())


def get_task_pack(name: str) -> TaskPack:
    try:
        return _TASK_PACKS[name]
    except KeyError as exc:
        raise ValueError(f'Unknown task pack: {name}') from exc


def render_task_prompt(name: str, context: str | None = None) -> str:
    pack = get_task_pack(name)
    return pack.prompt_template.format(context=context or 'No additional context provided.')


def task_pack_payload(pack: TaskPack) -> dict[str, Any]:
    return {
        'name': pack.name,
        'description': pack.description,
        'recommended_scenario': pack.recommended_scenario,
        'prompt_template': pack.prompt_template,
        'acceptance_criteria': list(pack.acceptance_criteria),
    }
