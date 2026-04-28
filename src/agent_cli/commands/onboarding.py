from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from textwrap import dedent
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

from agent_runtime import build_runtime

console = Console()
template_app = typer.Typer(help='Create starter project templates.')


def register(app: typer.Typer) -> None:
    @app.command('init')
    def init_config(
        path: str = typer.Option('easy-agent.yml', '--path', help='Config file to create.'),
        provider: str = typer.Option('mock', '--provider', help='Provider preset: mock or deepseek.'),
        force: bool = typer.Option(False, '--force', help='Overwrite an existing config file.'),
    ) -> None:
        target = Path(path)
        if target.exists() and not force:
            raise typer.BadParameter(f'{target} already exists; pass --force to overwrite it.')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_starter_config(provider), encoding='utf-8')
        console.print(f'[green]Created[/green] {target}')
        console.print('Next: easy-agent quickstart')

    @app.command('quickstart')
    def quickstart(
        provider: str = typer.Option('mock', '--provider', help='Provider preset: mock or deepseek.'),
    ) -> None:
        if provider == 'deepseek' and not os.environ.get('DEEPSEEK_API_KEY'):
            raise typer.BadParameter('DEEPSEEK_API_KEY is not set. Use --provider mock for offline quickstart.')
        config_path = Path('.easy-agent/quickstart/easy-agent.yml')
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.safe_dump(_quickstart_config(provider), sort_keys=False), encoding='utf-8')

        async def _run() -> None:
            runtime = build_runtime(config_path)
            try:
                result = await runtime.run('Run the offline quickstart and echo the task once.')
                run_id = str(result.get('run_id') or '')
                console.print_json(json.dumps(result, ensure_ascii=False))
                if run_id:
                    console.print('\nNext debugging commands:')
                    console.print(f'easy-agent runs show {run_id} -c {config_path}')
                    console.print(f'easy-agent runs explain {run_id} -c {config_path}')
                    console.print(f'easy-agent traces export {run_id} -c {config_path}')
            finally:
                await runtime.aclose()

        asyncio.run(_run())


@template_app.command('list')
def list_templates() -> None:
    table = Table(title='easy-agent templates')
    table.add_column('Name', style='cyan')
    table.add_column('Description', style='green')
    for name, template in _templates().items():
        table.add_row(name, str(template['description']))
    console.print(table)


@template_app.command('create')
def create_template(
    name: str = typer.Argument(..., help='Template name.'),
    dest: str = typer.Argument(..., help='Destination directory.'),
    force: bool = typer.Option(False, '--force', help='Overwrite generated files when they already exist.'),
) -> None:
    templates = _templates()
    if name not in templates:
        raise typer.BadParameter(f"Unknown template '{name}'. Run 'easy-agent template list'.")
    destination = Path(dest)
    files = templates[name]['files']
    if not isinstance(files, dict):
        raise RuntimeError(f"Template '{name}' is invalid.")
    collisions = [destination / relative for relative in files if (destination / relative).exists()]
    if collisions and not force:
        joined = ', '.join(str(item) for item in collisions)
        raise typer.BadParameter(f'Generated files already exist: {joined}. Pass --force to overwrite them.')
    for relative, content in files.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding='utf-8')
    console.print(f'[green]Created template[/green] {name} at {destination}')


def _starter_config(provider: str, sensitive_tools: list[str] | None = None) -> str:
    if provider not in {'mock', 'deepseek'}:
        raise typer.BadParameter('provider must be mock or deepseek')
    model_block = (
        dedent(
            """
model:
  provider: mock
  protocol: mock
  model: mock-agent
  base_url: mock://local
  api_key_env: EASY_AGENT_MOCK_API_KEY
"""
        ).strip()
        if provider == 'mock'
        else dedent(
            """
model:
  provider: deepseek
  protocol: auto
  model: deepseek-chat
  base_url: https://api.deepseek.com
  api_key_env: DEEPSEEK_API_KEY
"""
        ).strip()
    )
    body = """graph:
  name: starter
  entrypoint: assistant
  agents:
    - name: assistant
      description: A focused starter assistant.
      system_prompt: |
        You are a concise assistant. Use python_echo once when it helps, then produce a final answer.
      tools:
        - python_echo
      max_iterations: 4
  nodes: []

skills:
  - path: skills/examples

storage:
  path: .easy-agent
  database: state.db

security:
"""
    if sensitive_tools:
        body += """  human_loop:
    mode: deferred
    sensitive_tools:
"""
        body += ''.join(f'      - {tool}\n' for tool in sensitive_tools)
    body += """  sandbox:
    mode: auto
    working_root: .
"""
    return f'{model_block}\n\n{body}'


def _quickstart_config(provider: str) -> dict[str, Any]:
    if provider not in {'mock', 'deepseek'}:
        raise typer.BadParameter('provider must be mock or deepseek')
    model = {
        'provider': 'mock',
        'protocol': 'mock',
        'model': 'mock-agent',
        'base_url': 'mock://local',
        'api_key_env': 'EASY_AGENT_MOCK_API_KEY',
    }
    if provider == 'deepseek':
        model = {
            'provider': 'deepseek',
            'protocol': 'auto',
            'model': 'deepseek-chat',
            'base_url': 'https://api.deepseek.com',
            'api_key_env': 'DEEPSEEK_API_KEY',
        }
    return {
        'model': model,
        'graph': {
            'name': 'quickstart',
            'entrypoint': 'assistant',
            'agents': [
                {
                    'name': 'assistant',
                    'description': 'Offline quickstart assistant.',
                    'system_prompt': 'Use python_echo at most once, then write a concise final answer.',
                    'tools': ['python_echo'],
                    'max_iterations': 4,
                }
            ],
            'nodes': [],
        },
        'skills': [{'path': str(_repo_root() / 'skills' / 'examples').replace('\\', '/')}],
        'storage': {'path': '.easy-agent/quickstart', 'database': 'state.db'},
        'security': {'sandbox': {'mode': 'auto', 'working_root': '.'}},
    }


def _templates() -> dict[str, dict[str, Any]]:
    return {
        'basic-agent': {
            'description': 'Single mock-backed agent for local development.',
            'files': _template_files('basic-agent', 'A single local assistant.', _starter_config('mock')),
        },
        'tool-agent': {
            'description': 'Single agent with python_echo mounted as a starter tool.',
            'files': _template_files('tool-agent', 'A tool-using local assistant.', _starter_config('mock')),
        },
        'human-approval-agent': {
            'description': 'Starter config with python_echo marked as a sensitive tool.',
            'files': _template_files(
                'human-approval-agent',
                'A starter approval workflow.',
                _starter_config('mock', sensitive_tools=['python_echo']),
            ),
        },
        'longrun-harness': {
            'description': 'Initializer, worker, and evaluator harness starter.',
            'files': _template_files('longrun-harness', 'A minimal long-running harness starter.', _harness_template_config()),
        },
    }


def _template_files(name: str, description: str, config: str) -> dict[str, str]:
    return {
        'easy-agent.yml': config,
        'README.md': dedent(
            f"""
            # {name}

            {description}

            ## Run

            ```bash
            easy-agent doctor -c easy-agent.yml
            easy-agent run "Hello from the template" -c easy-agent.yml
            ```
            """
        ).lstrip(),
        '.env.local.example': 'DEEPSEEK_API_KEY=<SECRET>\nSERPAPI_API_KEY=<SECRET>\n',
    }


def _harness_template_config() -> str:
    return _starter_config('mock') + dedent(
        """

        harnesses:
          - name: delivery_loop
            initializer_agent: assistant
            worker_target: assistant
            evaluator_agent: assistant
            completion_contract: Finish one useful increment and summarize the outcome.
            artifacts_dir: .easy-agent/harness
            max_cycles: 2
            max_replans: 0
        """
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]
