from __future__ import annotations

from pathlib import Path

import pytest

from agent_common.models import RunStatus
from agent_runtime import build_runtime


@pytest.mark.asyncio
async def test_mock_provider_runs_tool_flow_offline(tmp_path: Path) -> None:
    config_path = tmp_path / 'easy-agent.yml'
    storage_path = str(tmp_path / 'state').replace('\\', '/')
    skill_path = str((Path.cwd() / 'skills' / 'examples').resolve()).replace('\\', '/')
    config_path.write_text(
        f"""
model:
  provider: mock
  protocol: mock
  model: mock-agent
  base_url: mock://local
  api_key_env: EASY_AGENT_MOCK_API_KEY
graph:
  entrypoint: assistant
  agents:
    - name: assistant
      tools:
        - python_echo
      max_iterations: 4
storage:
  path: {storage_path}
  database: state.db
skills:
  - path: {skill_path}
security:
  sandbox:
    mode: process
    working_root: .
""",
        encoding='utf-8',
    )
    runtime = build_runtime(config_path)
    try:
        result = await runtime.run('Echo this once.')
        run_id = str(result['run_id'])
        trace = runtime.store.load_trace(run_id)
    finally:
        await runtime.aclose()

    assert result['status'] == RunStatus.SUCCEEDED.value
    assert 'Mock final answer based on tool result' in str(result['result'])
    assert any(event['kind'] == 'tool_call_succeeded' for event in trace['events'])
