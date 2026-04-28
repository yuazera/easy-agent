from __future__ import annotations

from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch
from typer.testing import CliRunner

from agent_cli.app import app


def test_init_creates_mock_config_and_protects_existing_file(tmp_path: Path) -> None:
    runner = CliRunner()
    config_path = tmp_path / 'easy-agent.yml'

    first = runner.invoke(app, ['init', '--path', str(config_path), '--provider', 'mock'])
    second = runner.invoke(app, ['init', '--path', str(config_path), '--provider', 'mock'])

    assert first.exit_code == 0
    assert 'Created' in first.output
    assert 'provider: mock' in config_path.read_text(encoding='utf-8')
    assert 'protocol: mock' in config_path.read_text(encoding='utf-8')
    assert second.exit_code != 0
    assert 'already exists' in second.output


def test_template_commands_list_and_create(tmp_path: Path) -> None:
    runner = CliRunner()
    destination = tmp_path / 'starter'

    listed = runner.invoke(app, ['template', 'list'])
    created = runner.invoke(app, ['template', 'create', 'basic-agent', str(destination)])

    assert listed.exit_code == 0
    assert 'basic-agent' in listed.output
    assert 'longrun-harness' in listed.output
    assert created.exit_code == 0
    assert (destination / 'easy-agent.yml').exists()
    assert (destination / '.env.local.example').read_text(encoding='utf-8') == (
        'DEEPSEEK_API_KEY=<SECRET>\nSERPAPI_API_KEY=<SECRET>\n'
    )


def test_quickstart_runs_offline_mock_provider(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ['quickstart', '--provider', 'mock'])

    assert result.exit_code == 0
    assert 'Mock final answer based on tool result' in result.output
    assert 'easy-agent runs explain' in result.output
