from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

from agent_cli.shared import with_runtime
from agent_config.app import load_config
from agent_runtime import EasyAgentRuntime, build_runtime

console = Console()
skills_app = typer.Typer(help='Inspect registered skills.')
skills_catalog_app = typer.Typer(help='Inspect and install local skill catalog entries.')
mcp_app = typer.Typer(help='Inspect discovered MCP tools.')
plugins_app = typer.Typer(help='Inspect loaded plugins.')
teams_app = typer.Typer(help='Inspect configured agent teams.')
federation_app = typer.Typer(help='Inspect and serve federated agent surfaces.')
federation_auth_app = typer.Typer(help='Manage federation remote authorization.')
workbench_app = typer.Typer(help='Inspect and manage isolated workbench sessions.')
mcp_auth_app = typer.Typer(help='Manage MCP remote authorization.')
mcp_roots_app = typer.Typer(help='Inspect and refresh MCP roots.')
mcp_resources_app = typer.Typer(help='Inspect and manage MCP resources.')
mcp_prompts_app = typer.Typer(help='Inspect MCP prompts.')
mcp_app.add_typer(mcp_auth_app, name='auth')
mcp_app.add_typer(mcp_roots_app, name='roots')
mcp_app.add_typer(mcp_resources_app, name='resources')
mcp_app.add_typer(mcp_prompts_app, name='prompts')
federation_app.add_typer(federation_auth_app, name='auth')
skills_app.add_typer(skills_catalog_app, name='catalog')


@skills_app.command('list')
def list_skills(config: str = typer.Option('easy-agent.yml', '-c', '--config')) -> None:
    runtime = build_runtime(config)
    try:
        table = Table(title='skills')
        table.add_column('Name', style='cyan')
        table.add_column('Description', style='green')
        for skill in runtime.skills:
            table.add_row(skill.name, skill.description)
        console.print(table)
    finally:
        asyncio.run(runtime.aclose())


@mcp_app.command('list')
def list_mcp(config: str = typer.Option('easy-agent.yml', '-c', '--config')) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        table = Table(title='mcp tools')
        table.add_column('Server', style='cyan')
        table.add_column('Transport', style='green')
        table.add_column('Tool', style='yellow')
        servers = await runtime.mcp_manager.list_servers()
        for server_name, tools in servers.items():
            transport = runtime.config.mcp_map[server_name].transport
            for tool in tools:
                table.add_row(server_name, transport, tool.name)
        console.print(table)

    asyncio.run(with_runtime(config, _run))


@mcp_app.command('doctor')
def doctor_mcp(
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
    output_format: str = typer.Option('pretty', '--format', help='Output format: pretty or json.'),
) -> None:
    loaded = load_config(config)
    checks = [_mcp_server_check(server.model_dump(mode='json')) for server in loaded.mcp]
    if not checks:
        checks.append({'name': 'mcp', 'status': 'ok', 'message': 'No MCP servers are configured.', 'action': 'Add mcp entries when connector tools are needed.'})
    payload = {'summary': _status_summary(checks), 'checks': checks}
    if output_format == 'json':
        console.print_json(json.dumps(payload, ensure_ascii=False))
        return
    if output_format != 'pretty':
        raise typer.BadParameter('format must be pretty or json')
    table = Table(title='mcp doctor')
    table.add_column('Status', style='cyan')
    table.add_column('Server', style='green')
    table.add_column('Message')
    table.add_column('Action')
    for check in checks:
        table.add_row(str(check['status']), str(check['name']), str(check['message']), str(check['action']))
    console.print(table)


@mcp_app.command('test')
def test_mcp(
    server_name: str = typer.Argument(..., help='Configured MCP server name.'),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
    live: bool = typer.Option(False, '--live', help='Start the MCP server and list tools. Default is static only.'),
    output_format: str = typer.Option('pretty', '--format', help='Output format: pretty or json.'),
) -> None:
    loaded = load_config(config)
    server = loaded.mcp_map.get(server_name)
    if server is None:
        raise typer.BadParameter(f'Unknown MCP server: {server_name}')
    check = _mcp_server_check(server.model_dump(mode='json'))
    payload: dict[str, Any] = {'server': server_name, 'mode': 'live' if live else 'static', 'checks': [check]}
    if live:
        async def _run(runtime: EasyAgentRuntime) -> None:
            tools = await runtime.mcp_manager.list_servers()
            payload['tools'] = [tool.name for tool in tools.get(server_name, [])]

        asyncio.run(with_runtime(config, _run))
    if output_format == 'json':
        console.print_json(json.dumps(payload, ensure_ascii=False, default=str))
        return
    if output_format != 'pretty':
        raise typer.BadParameter('format must be pretty or json')
    table = Table(title=f'mcp test: {server_name}')
    table.add_column('Field', style='cyan')
    table.add_column('Value', style='green')
    table.add_row('mode', str(payload['mode']))
    table.add_row('status', str(check['status']))
    table.add_row('message', str(check['message']))
    if 'tools' in payload:
        table.add_row('tools', ', '.join(str(item) for item in payload.get('tools', [])))
    console.print(table)
    if check['status'] == 'error':
        raise typer.Exit(1)


@mcp_roots_app.command('list')
def list_mcp_roots(
    server_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.mcp_manager.list_roots(server_name), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@mcp_roots_app.command('refresh')
def refresh_mcp_roots(
    server_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.mcp_manager.refresh_roots(server_name), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@mcp_resources_app.command('list')
def list_mcp_resources(
    server_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.mcp_manager.list_resources(server_name), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@mcp_resources_app.command('read')
def read_mcp_resource(
    server_name: str = typer.Argument(...),
    uri: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.mcp_manager.read_resource(server_name, uri), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@mcp_resources_app.command('templates')
def list_mcp_resource_templates(
    server_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(
            json.dumps(await runtime.mcp_manager.list_resource_templates(server_name), ensure_ascii=False)
        )

    asyncio.run(with_runtime(config, _run))


@mcp_resources_app.command('subscribe')
def subscribe_mcp_resource(
    server_name: str = typer.Argument(...),
    uri: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.mcp_manager.subscribe_resource(server_name, uri), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@mcp_resources_app.command('unsubscribe')
def unsubscribe_mcp_resource(
    server_name: str = typer.Argument(...),
    uri: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(
            json.dumps(await runtime.mcp_manager.unsubscribe_resource(server_name, uri), ensure_ascii=False)
        )

    asyncio.run(with_runtime(config, _run))


@mcp_prompts_app.command('list')
def list_mcp_prompts(
    server_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.mcp_manager.list_prompts(server_name), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@mcp_prompts_app.command('get')
def get_mcp_prompt(
    server_name: str = typer.Argument(...),
    prompt_name: str = typer.Argument(...),
    arguments: str | None = typer.Option(None, '--arguments'),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        payload = json.loads(arguments) if arguments else None
        console.print_json(
            json.dumps(await runtime.mcp_manager.get_prompt(server_name, prompt_name, arguments=payload), ensure_ascii=False)
        )

    asyncio.run(with_runtime(config, _run))


@mcp_auth_app.command('status')
def mcp_auth_status(
    server_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    runtime = build_runtime(config)
    try:
        console.print_json(json.dumps(runtime.mcp_manager.auth_status(server_name), ensure_ascii=False))
    finally:
        asyncio.run(runtime.aclose())


@mcp_auth_app.command('login')
def mcp_auth_login(
    server_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        async def _redirect(url: str) -> None:
            console.print(f'Open this URL to authorize:\n{url}')

        async def _callback() -> tuple[str, str | None]:
            code = await asyncio.to_thread(console.input, 'Authorization code: ')
            state = await asyncio.to_thread(console.input, 'Returned state (blank if none): ')
            return code.strip(), state.strip() or None

        runtime.mcp_manager.set_oauth_handlers(_redirect, _callback)
        await runtime.mcp_manager.authorize(server_name)
        console.print_json(json.dumps(runtime.mcp_manager.auth_status(server_name), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@mcp_auth_app.command('logout')
def mcp_auth_logout(
    server_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        await runtime.mcp_manager.logout(server_name)
        console.print_json(json.dumps({'server': server_name, 'status': 'logged_out'}, ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@plugins_app.command('list')
def list_plugins(config: str = typer.Option('easy-agent.yml', '-c', '--config')) -> None:
    runtime = build_runtime(config)
    try:
        table = Table(title='plugins')
        table.add_column('Source', style='cyan')
        for source in runtime.loaded_sources:
            table.add_row(source)
        console.print(table)
    finally:
        asyncio.run(runtime.aclose())


@teams_app.command('list')
def list_teams(config: str = typer.Option('easy-agent.yml', '-c', '--config')) -> None:
    runtime = build_runtime(config)
    try:
        table = Table(title='teams')
        table.add_column('Name', style='cyan')
        table.add_column('Mode', style='green')
        table.add_column('Members', style='yellow')
        table.add_column('Max Turns', style='magenta')
        table.add_column('Termination', style='white')
        for team in runtime.config.graph.teams:
            table.add_row(
                team.name,
                team.mode.value,
                ', '.join(team.members),
                str(team.max_turns),
                team.termination_text,
            )
        console.print(table)
    finally:
        asyncio.run(runtime.aclose())


@federation_app.command('list')
def list_federation(config: str = typer.Option('easy-agent.yml', '-c', '--config')) -> None:
    runtime = build_runtime(config)
    try:
        table = Table(title='federation')
        table.add_column('Type', style='cyan')
        table.add_column('Name', style='green')
        table.add_column('Target', style='yellow')
        for remote in runtime.config.federation.remotes:
            table.add_row('remote', remote.name, remote.base_url)
        for export in runtime.config.federation.exports:
            table.add_row('export', export.name, f'{export.target_type}:{export.target}')
        console.print(table)
    finally:
        asyncio.run(runtime.aclose())


@federation_app.command('graph')
def graph_federation(
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
    output_format: str = typer.Option('json', '--format', help='Output format: json, mermaid, or html.'),
    output: str | None = typer.Option(None, '-o', '--output', help='Optional output file for mermaid or html.'),
) -> None:
    runtime = build_runtime(config)
    try:
        payload = _federation_graph_payload(runtime)
    finally:
        asyncio.run(runtime.aclose())
    if output_format == 'json':
        console.print_json(json.dumps(payload, ensure_ascii=False, default=str))
        return
    if output_format == 'mermaid':
        content = _federation_graph_mermaid(payload)
    elif output_format == 'html':
        content = _federation_graph_html(payload)
    else:
        raise typer.BadParameter('format must be json, mermaid, or html')
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding='utf-8')
        console.print_json(json.dumps({'output': str(output_path), 'format': output_format}, ensure_ascii=False))
    else:
        console.print(content)


@federation_app.command('inspect')
def inspect_federation(
    remote_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.inspect_remote(remote_name), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_auth_app.command('status')
def federation_auth_status(
    remote_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    runtime = build_runtime(config)
    try:
        console.print_json(json.dumps(runtime.federation_auth_status(remote_name), ensure_ascii=False))
    finally:
        asyncio.run(runtime.aclose())


@plugins_app.command('doctor')
def doctor_plugins(
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
    output_format: str = typer.Option('pretty', '--format', help='Output format: pretty or json.'),
) -> None:
    from agent_config.app import load_config

    loaded = load_config(config)
    checks: list[dict[str, str]] = []
    for source in loaded.plugins:
        path = Path(source)
        if path.exists():
            checks.append({'name': source, 'status': 'ok', 'message': 'Local plugin path exists.', 'action': 'No action needed.'})
        else:
            checks.append({'name': source, 'status': 'warn', 'message': 'Plugin is treated as an entry point and was not resolved statically.', 'action': 'Install the package that exposes this entry point before runtime load.'})
    for skill_source in loaded.skills:
        path = Path(skill_source.path)
        manifest = path / 'skill.yaml' if path.is_dir() else path
        checks.append(
            {
                'name': skill_source.path,
                'status': 'ok' if manifest.exists() or skill_source.optional else 'warn',
                'message': 'Skill path is available.' if manifest.exists() else 'Skill path is missing.',
                'action': 'No action needed.' if manifest.exists() else 'Install the skill or mark the source optional.',
            }
        )
    if not checks:
        checks.append({'name': 'plugins', 'status': 'ok', 'message': 'No plugins are configured.', 'action': 'No action needed.'})
    payload = {'checks': checks}
    if output_format == 'json':
        console.print_json(json.dumps(payload, ensure_ascii=False))
        return
    table = Table(title='plugins doctor')
    table.add_column('Status', style='cyan')
    table.add_column('Name', style='green')
    table.add_column('Message')
    table.add_column('Action')
    for check in checks:
        table.add_row(check['status'], check['name'], check['message'], check['action'])
    console.print(table)


@skills_catalog_app.command('list')
def list_skill_catalog(
    root: str = typer.Option('skills', '--root', help='Local skills root.'),
    output_format: str = typer.Option('pretty', '--format', help='Output format: pretty or json.'),
) -> None:
    payload = _local_skill_catalog(Path(root))
    if output_format == 'json':
        console.print_json(json.dumps({'skills': payload}, ensure_ascii=False))
        return
    table = Table(title='local skill catalog')
    table.add_column('Name', style='cyan')
    table.add_column('Risk', style='yellow')
    table.add_column('Source', style='green')
    table.add_column('Description')
    for item in payload:
        table.add_row(str(item['name']), str(item.get('risk') or '-'), str(item['path']), str(item.get('description') or '-'))
    console.print(table)


@skills_catalog_app.command('install')
def install_skill_catalog(
    name: str = typer.Argument(..., help='Skill name from skills catalog list.'),
    root: str = typer.Option('skills', '--root', help='Local skills root.'),
    target: str = typer.Option('skills/installed', '--target', help='Destination directory for installed skills.'),
    force: bool = typer.Option(False, '--force', help='Overwrite an existing installed copy.'),
) -> None:
    catalog = _local_skill_catalog(Path(root))
    match = next((item for item in catalog if item['name'] == name), None)
    if match is None:
        raise typer.BadParameter(f'Unknown skill: {name}')
    source = Path(str(match['path']))
    destination = Path(target) / name
    if destination.exists() and not force:
        raise typer.BadParameter(f'{destination} already exists; pass --force to overwrite.')
    shutil.copytree(source, destination, dirs_exist_ok=force)
    console.print_json(json.dumps({'skill': name, 'source': str(source), 'destination': str(destination)}, ensure_ascii=False))


def _local_skill_catalog(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for manifest in sorted(root.rglob('skill.yaml')):
        payload = yaml.safe_load(manifest.read_text(encoding='utf-8')) or {}
        if not isinstance(payload, dict):
            continue
        items.append(
            {
                'name': str(payload.get('name') or manifest.parent.name),
                'description': str(payload.get('description') or ''),
                'entry_type': str(payload.get('entry_type') or ''),
                'risk': str(payload.get('risk') or 'low'),
                'dependencies': payload.get('dependencies') if isinstance(payload.get('dependencies'), list) else [],
                'smoke_prompt': str(payload.get('smoke_prompt') or ''),
                'path': str(manifest.parent),
            }
        )
    return items


@federation_auth_app.command('login')
def federation_auth_login(
    remote_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        async def _redirect(url: str) -> None:
            console.print(f'Open this URL to authorize:\n{url}')

        async def _callback() -> tuple[str, str | None]:
            code = await asyncio.to_thread(console.input, 'Authorization code: ')
            state = await asyncio.to_thread(console.input, 'Returned state (blank if none): ')
            return code.strip(), state.strip() or None

        runtime.federation_manager.set_oauth_handlers(_redirect, _callback)
        console.print_json(json.dumps(await runtime.federation_authorize(remote_name), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_auth_app.command('refresh')
def federation_auth_refresh(
    remote_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.federation_refresh_auth(remote_name), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_auth_app.command('logout')
def federation_auth_logout(
    remote_name: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        await runtime.federation_logout(remote_name)
        console.print_json(json.dumps({'remote': remote_name, 'status': 'logged_out'}, ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_app.command('tasks')
def list_federation_tasks(
    remote_name: str = typer.Argument(...),
    page_token: str | None = typer.Option(None, '--page-token'),
    page_size: int | None = typer.Option(None, '--page-size'),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(
            json.dumps(
                await runtime.list_remote_tasks(remote_name, page_token=page_token, page_size=page_size),
                ensure_ascii=False,
            )
        )

    asyncio.run(with_runtime(config, _run))


@federation_app.command('events')
def list_federation_events(
    remote_name: str = typer.Argument(...),
    task_id: str = typer.Argument(...),
    after_sequence: int = typer.Option(0, '--after-sequence'),
    page_token: str | None = typer.Option(None, '--page-token'),
    page_size: int | None = typer.Option(None, '--page-size'),
    stream: bool = typer.Option(False, '--stream'),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        payload: Any
        if stream:
            payload = await runtime.stream_remote_task_events(remote_name, task_id, after_sequence)
        else:
            payload = await runtime.list_remote_task_events(
                remote_name,
                task_id,
                after_sequence,
                page_token=page_token,
                page_size=page_size,
            )
        console.print_json(json.dumps(payload, ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_app.command('cancel-task')
def cancel_federation_task(
    remote_name: str = typer.Argument(...),
    task_id: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.cancel_remote_task(remote_name, task_id), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_app.command('subscriptions')
def list_federation_subscriptions(
    remote_name: str = typer.Argument(...),
    task_id: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.list_remote_subscriptions(remote_name, task_id), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_app.command('renew-subscription')
def renew_federation_subscription(
    remote_name: str = typer.Argument(...),
    task_id: str = typer.Argument(...),
    subscription_id: str = typer.Argument(...),
    lease_seconds: int | None = typer.Option(None, '--lease-seconds'),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(
            json.dumps(
                await runtime.renew_remote_subscription(
                    remote_name,
                    task_id,
                    subscription_id,
                    lease_seconds=lease_seconds,
                ),
                ensure_ascii=False,
            )
        )

    asyncio.run(with_runtime(config, _run))


@federation_app.command('cancel-subscription')
def cancel_federation_subscription(
    remote_name: str = typer.Argument(...),
    task_id: str = typer.Argument(...),
    subscription_id: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.cancel_remote_subscription(remote_name, task_id, subscription_id), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_app.command('push-set')
def set_federation_push_notification(
    remote_name: str = typer.Argument(...),
    task_id: str = typer.Argument(...),
    callback_url: str = typer.Argument(...),
    lease_seconds: int | None = typer.Option(None, '--lease-seconds'),
    from_sequence: int = typer.Option(0, '--from-sequence'),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(
            json.dumps(
                await runtime.set_remote_push_notification(
                    remote_name,
                    task_id,
                    callback_url,
                    lease_seconds=lease_seconds,
                    from_sequence=from_sequence,
                ),
                ensure_ascii=False,
            )
        )

    asyncio.run(with_runtime(config, _run))


@federation_app.command('push-get')
def get_federation_push_notification(
    remote_name: str = typer.Argument(...),
    task_id: str = typer.Argument(...),
    config_id: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.get_remote_push_notification(remote_name, task_id, config_id), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_app.command('push-list')
def list_federation_push_notifications(
    remote_name: str = typer.Argument(...),
    task_id: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.list_remote_push_notifications(remote_name, task_id), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_app.command('push-delete')
def delete_federation_push_notification(
    remote_name: str = typer.Argument(...),
    task_id: str = typer.Argument(...),
    config_id: str = typer.Argument(...),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(json.dumps(await runtime.delete_remote_push_notification(remote_name, task_id, config_id), ensure_ascii=False))

    asyncio.run(with_runtime(config, _run))


@federation_app.command('send-subscribe')
def send_subscribe_federation(
    remote_name: str = typer.Argument(...),
    target: str = typer.Argument(...),
    input_text: str = typer.Argument(...),
    callback_url: str = typer.Argument(...),
    session_id: str | None = typer.Option(None, '--session-id'),
    lease_seconds: int | None = typer.Option(None, '--lease-seconds'),
    from_sequence: int = typer.Option(0, '--from-sequence'),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(
            json.dumps(
                await runtime.send_subscribe_remote(
                    remote_name,
                    target,
                    input_text,
                    callback_url,
                    session_id=session_id,
                    lease_seconds=lease_seconds,
                    from_sequence=from_sequence,
                ),
                ensure_ascii=False,
            )
        )

    asyncio.run(with_runtime(config, _run))


@federation_app.command('resubscribe')
def resubscribe_federation(
    remote_name: str = typer.Argument(...),
    task_id: str = typer.Argument(...),
    from_sequence: int = typer.Option(0, '--from-sequence'),
    callback_url: str | None = typer.Option(None, '--callback-url'),
    lease_seconds: int | None = typer.Option(None, '--lease-seconds'),
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    async def _run(runtime: EasyAgentRuntime) -> None:
        console.print_json(
            json.dumps(
                await runtime.resubscribe_remote_task(
                    remote_name,
                    task_id,
                    from_sequence=from_sequence,
                    callback_url=callback_url,
                    lease_seconds=lease_seconds,
                ),
                ensure_ascii=False,
            )
        )

    asyncio.run(with_runtime(config, _run))


def _mcp_server_check(server: dict[str, Any]) -> dict[str, str]:
    name = str(server.get('name') or 'mcp')
    transport = str(server.get('transport') or 'stdio')
    messages: list[str] = []
    actions: list[str] = []
    status = 'ok'
    command = server.get('command')
    if transport == 'stdio':
        tokens = command if isinstance(command, list) else []
        executable = str(tokens[0]) if tokens else ''
        if executable and shutil.which(executable):
            messages.append(f'{executable} is available.')
        elif executable:
            status = 'warn'
            messages.append(f'{executable} is not on PATH.')
            actions.append(f'Install {executable} or update the MCP command.')
        else:
            status = 'error'
            messages.append('stdio MCP server has no command.')
            actions.append('Set command for the MCP server.')
        roots = server.get('roots')
        if not roots:
            status = 'warn' if status != 'error' else status
            messages.append('No explicit roots are declared.')
            actions.append('Declare roots to make filesystem boundaries clear.')
    elif transport in {'http_sse', 'streamable_http'}:
        if not (server.get('url') or server.get('rpc_url') or server.get('sse_url')):
            status = 'error'
            messages.append('Remote MCP URL is missing.')
            actions.append('Set url, rpc_url, or sse_url.')
        else:
            messages.append(f'{transport} remote URL is configured.')
        raw_auth = server.get('auth')
        auth: dict[str, Any] = raw_auth if isinstance(raw_auth, dict) else {}
        token_env = str(auth.get('token_env') or '')
        if token_env and not os.environ.get(token_env):
            status = 'warn' if status != 'error' else status
            messages.append(f'{token_env} is missing.')
            actions.append(f'Set {token_env} before live calls.')
    else:
        status = 'error'
        messages.append(f'Unsupported MCP transport: {transport}.')
        actions.append('Use stdio, http_sse, or streamable_http.')
    return {
        'name': name,
        'status': status,
        'message': ' '.join(messages) if messages else 'MCP server config is statically valid.',
        'action': ' '.join(actions) if actions else 'No action needed.',
    }


def _status_summary(items: list[dict[str, str]]) -> dict[str, int]:
    return {
        'ok': sum(1 for item in items if item.get('status') == 'ok'),
        'warn': sum(1 for item in items if item.get('status') == 'warn'),
        'error': sum(1 for item in items if item.get('status') == 'error'),
    }


def _federation_graph_payload(runtime: EasyAgentRuntime) -> dict[str, Any]:
    config = runtime.config.federation
    return {
        'server': {
            'base_path': config.server.base_path,
            'host': config.server.host,
            'port': config.server.port,
        },
        'remotes': [
            {'name': remote.name, 'base_url': remote.base_url, 'push_preference': remote.push_preference}
            for remote in config.remotes
        ],
        'exports': [
            {'name': item.name, 'target_type': item.target_type, 'target': item.target}
            for item in config.exports
        ],
        'recent_tasks': runtime.store.list_federated_tasks()[:20],
    }


def _federation_graph_mermaid(payload: dict[str, Any]) -> str:
    lines = ['graph LR', '  local[easy-agent local]']
    raw_remotes = payload.get('remotes')
    remotes: list[Any] = raw_remotes if isinstance(raw_remotes, list) else []
    raw_exports = payload.get('exports')
    exports: list[Any] = raw_exports if isinstance(raw_exports, list) else []
    for item_raw in exports:
        item = item_raw if isinstance(item_raw, dict) else {}
        name = _graph_id(str(item.get('name') or 'export'))
        lines.append(f'  local --> export_{name}[export: {name}]')
    for item_raw in remotes:
        item = item_raw if isinstance(item_raw, dict) else {}
        name = _graph_id(str(item.get('name') or 'remote'))
        lines.append(f'  local --> remote_{name}[remote: {name}]')
    return '\n'.join(lines) + '\n'


def _federation_graph_html(payload: dict[str, Any]) -> str:
    mermaid = _federation_graph_mermaid(payload)
    raw_json = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>easy-agent federation graph</title></head>
<body>
  <main>
    <h1>easy-agent federation graph</h1>
    <h2>Mermaid</h2>
    <pre>{mermaid}</pre>
    <h2>Raw JSON</h2>
    <pre>{raw_json}</pre>
  </main>
</body>
</html>
"""


def _graph_id(value: str) -> str:
    return ''.join(ch if ch.isalnum() else '_' for ch in value).strip('_') or 'node'


@federation_app.command('serve')
def serve_federation(
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    runtime = build_runtime(config)
    try:
        asyncio.run(runtime.start())
        status = runtime.serve_federation()
        console.print_json(json.dumps(status, ensure_ascii=False))
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        runtime.stop_federation()
    finally:
        asyncio.run(runtime.aclose())


@workbench_app.command('list')
def list_workbench(
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
    owner_run_id: str | None = typer.Option(None, '--run-id'),
) -> None:
    runtime = build_runtime(config)
    try:
        console.print_json(json.dumps(runtime.list_workbench_sessions(owner_run_id=owner_run_id), ensure_ascii=False))
    finally:
        asyncio.run(runtime.aclose())


@workbench_app.command('gc')
def gc_workbench(
    config: str = typer.Option('easy-agent.yml', '-c', '--config'),
) -> None:
    runtime = build_runtime(config)
    try:
        removed = runtime.gc_workbench_sessions()
        console.print_json(json.dumps({'removed_sessions': removed}, ensure_ascii=False))
    finally:
        asyncio.run(runtime.aclose())

