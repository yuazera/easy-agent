from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from types import TracebackType
from typing import Any

from agent_common.models import HumanLoopMode
from agent_runtime.reports import latest_report_payload
from agent_runtime.runtime import EasyAgentRuntime, build_runtime
from agent_runtime.tasks import render_task_prompt


class AgentApp:
    """Small Python facade over EasyAgentRuntime for product-style embedding."""

    def __init__(self, runtime: EasyAgentRuntime) -> None:
        self.runtime = runtime

    @classmethod
    def from_config(cls, config: str | Path = 'easy-agent.yml') -> AgentApp:
        return cls(build_runtime(config))

    @classmethod
    def from_runtime(cls, runtime: EasyAgentRuntime) -> AgentApp:
        return cls(runtime)

    async def arun(
        self,
        input_text: str,
        *,
        session_id: str | None = None,
        approval_mode: HumanLoopMode = HumanLoopMode.HYBRID,
    ) -> dict[str, Any]:
        return await self.runtime.run(input_text, session_id=session_id, approval_mode=approval_mode)

    def run(
        self,
        input_text: str,
        *,
        session_id: str | None = None,
        approval_mode: HumanLoopMode = HumanLoopMode.HYBRID,
    ) -> dict[str, Any]:
        return asyncio.run(self.arun(input_text, session_id=session_id, approval_mode=approval_mode))

    async def arun_task(
        self,
        pack: str,
        *,
        context: str | None = None,
        session_id: str | None = None,
        approval_mode: HumanLoopMode = HumanLoopMode.HYBRID,
    ) -> dict[str, Any]:
        return await self.arun(
            render_task_prompt(pack, context),
            session_id=session_id,
            approval_mode=approval_mode,
        )

    def run_task(
        self,
        pack: str,
        *,
        context: str | None = None,
        session_id: str | None = None,
        approval_mode: HumanLoopMode = HumanLoopMode.HYBRID,
    ) -> dict[str, Any]:
        return asyncio.run(
            self.arun_task(pack, context=context, session_id=session_id, approval_mode=approval_mode)
        )

    async def astream(
        self,
        input_text: str,
        *,
        session_id: str | None = None,
        approval_mode: HumanLoopMode = HumanLoopMode.HYBRID,
    ) -> AsyncIterator[dict[str, Any]]:
        async for event in self.runtime.stream(
            input_text,
            session_id=session_id,
            approval_mode=approval_mode,
        ):
            yield event

    def stream(
        self,
        input_text: str,
        *,
        session_id: str | None = None,
        approval_mode: HumanLoopMode = HumanLoopMode.HYBRID,
    ) -> list[dict[str, Any]]:
        async def _collect() -> list[dict[str, Any]]:
            return [
                event
                async for event in self.astream(
                    input_text,
                    session_id=session_id,
                    approval_mode=approval_mode,
                )
            ]

        return asyncio.run(_collect())

    async def aresume(
        self,
        run_id: str,
        checkpoint_id: int | None = None,
        *,
        fork: bool = False,
        approval_mode: HumanLoopMode = HumanLoopMode.HYBRID,
    ) -> dict[str, Any]:
        return await self.runtime.resume(run_id, checkpoint_id, fork=fork, approval_mode=approval_mode)

    def resume(
        self,
        run_id: str,
        checkpoint_id: int | None = None,
        *,
        fork: bool = False,
        approval_mode: HumanLoopMode = HumanLoopMode.HYBRID,
    ) -> dict[str, Any]:
        return asyncio.run(
            self.aresume(run_id, checkpoint_id, fork=fork, approval_mode=approval_mode)
        )

    def report(
        self,
        *,
        config: str | Path = 'easy-agent.yml',
        benchmark_report: str | Path = '.easy-agent/benchmark-report.json',
        public_eval_report: str | Path = '.easy-agent/public-eval-report.json',
        real_network_report: str | Path = '.easy-agent/real-network-report.json',
        run_limit: int = 50,
    ) -> dict[str, Any]:
        return latest_report_payload(
            Path(config),
            benchmark_report=Path(benchmark_report),
            public_eval_report=Path(public_eval_report),
            real_network_report=Path(real_network_report),
            run_limit=run_limit,
        )

    def trace(self, run_id: str, *, tree: bool = True) -> dict[str, Any]:
        return self.runtime.store.load_trace_tree(run_id) if tree else self.runtime.store.load_trace(run_id)

    async def aclose(self) -> None:
        await self.runtime.aclose()

    def close(self) -> None:
        asyncio.run(self.aclose())

    async def __aenter__(self) -> AgentApp:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
