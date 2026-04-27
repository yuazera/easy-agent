from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_config.app import (
    ContainerExecutorOptions,
    ExecutorConfig,
    MicrovmExecutorOptions,
)
from agent_integrations.executors import (
    ContainerExecutorBackend,
    ExecutorSession,
    MicrovmExecutorBackend,
    build_executor_backends,
)
from agent_integrations.sandbox import (
    PreparedSubprocess,
    SandboxManager,
    SandboxMode,
    SandboxRequest,
    SandboxTarget,
)


class DummySandboxManager(SandboxManager):
    def __init__(self) -> None:
        super().__init__(
            mode=SandboxMode.PROCESS,
            targets=[SandboxTarget.COMMAND_SKILL, SandboxTarget.STDIO_MCP],
            env_allowlist=['PATH', 'TEMP', 'TMP'],
        )

    def prepare(self, request: SandboxRequest) -> PreparedSubprocess:
        return PreparedSubprocess(command=request.command, cwd=request.cwd, env=request.env)



def test_build_executor_backends_supports_multiple_kinds() -> None:
    sandbox = DummySandboxManager()
    backends = build_executor_backends(
        [
            ExecutorConfig(name='process', kind='process'),
            ExecutorConfig(
                name='containerized',
                kind='container',
                container=ContainerExecutorOptions(executable='podman', image='busybox'),
            ),
            ExecutorConfig(
                name='microvm-qemu',
                kind='microvm',
                microvm=MicrovmExecutorOptions(executable='qemu-system-x86_64', base_image='base.qcow2'),
            ),
        ],
        sandbox,
    )

    assert set(backends) == {'process', 'containerized', 'microvm-qemu'}
    assert backends['containerized'].kind == 'container'
    assert backends['microvm-qemu'].kind == 'microvm'
    assert backends['process'].describe()['capability_report']['filesystem_isolation'] == 'workbench_root_only'
    assert backends['containerized'].describe()['capability_report']['snapshot_restore_guarantee'] == 'checkpoint_image_when_enabled'
    assert backends['microvm-qemu'].describe()['capability_report']['env_allowlist'] == 'per_command_explicit_env'



def test_container_executor_wraps_podman_exec_command(tmp_path: Path) -> None:
    backend = ContainerExecutorBackend(
        ExecutorConfig(
            name='containerized',
            kind='container',
            default_timeout_seconds=5,
            container=ContainerExecutorOptions(
                executable='podman',
                image='busybox',
                workdir='/workspace',
                keepalive_command=['sleep', 'infinity'],
            ),
        ),
        DummySandboxManager(),
    )
    session = ExecutorSession('wb-1', tmp_path, 'containerized', {})
    with patch('agent_integrations.executors._command_exists', return_value=True), patch(
        'agent_integrations.executors._run_subprocess',
        return_value=SimpleNamespace(returncode=0, stdout='cid-123', stderr=''),
    ):
        prepared = backend.prepare_command(
            session,
            ['python', '-V'],
            env={'DEMO': '1'},
            timeout_seconds=5,
            target=SandboxTarget.COMMAND_SKILL,
        )

    assert prepared.command[:3] == ['podman', 'exec', '--env']
    assert 'python' in prepared.command



def test_microvm_executor_wraps_ssh_command(tmp_path: Path) -> None:
    backend = MicrovmExecutorBackend(
        ExecutorConfig(
            name='microvm-qemu',
            kind='microvm',
            default_timeout_seconds=5,
            microvm=MicrovmExecutorOptions(
                executable='qemu-system-x86_64',
                base_image='base.qcow2',
                ssh_user='agent',
                guest_workdir='/workspace',
            ),
        ),
        DummySandboxManager(),
    )
    session = ExecutorSession('wb-2', tmp_path, 'microvm-qemu', {})
    with patch('agent_integrations.executors._command_exists', return_value=True), patch(
        'agent_integrations.executors.subprocess.Popen',
        return_value=SimpleNamespace(pid=42),
    ), patch.object(MicrovmExecutorBackend, '_wait_for_ssh', return_value=None), patch.object(
        MicrovmExecutorBackend,
        '_sync_to_guest',
        return_value=None,
    ), patch.object(MicrovmExecutorBackend, '_qemu_img_executable', return_value=None):
        prepared = backend.prepare_command(
            session,
            ['python', '-V'],
            env={'DEMO': '1'},
            timeout_seconds=5,
            target=SandboxTarget.STDIO_MCP,
        )

    assert prepared.command[0] == 'ssh'
    assert '/workspace' in prepared.command[-1]
    assert 'python' in prepared.command[-1]

