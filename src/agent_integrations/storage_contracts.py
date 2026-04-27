from __future__ import annotations

from typing import Any, Protocol

from agent_common.models import ChatMessage, HumanRequest, HumanRequestStatus


class RunRepository(Protocol):
    def create_run(
        self,
        run_id: str,
        graph_name: str,
        input_payload: Any,
        session_id: str | None = None,
        run_kind: str = 'graph',
        parent_run_id: str | None = None,
        source_run_id: str | None = None,
        source_checkpoint_id: int | None = None,
        resume_strategy: str | None = None,
    ) -> None: ...
    def load_run(self, run_id: str) -> dict[str, Any]: ...
    def list_runs(self, limit: int = 50, status: str | None = None, run_kind: str | None = None) -> list[dict[str, Any]]: ...
    def load_run_summary(self, run_id: str) -> dict[str, Any]: ...
    def finish_run(self, run_id: str, status: str, output_payload: Any) -> None: ...


class SessionRepository(Protocol):
    def save_session_messages(self, session_id: str, graph_name: str, messages: list[ChatMessage]) -> None: ...
    def load_session_messages(self, session_id: str) -> list[ChatMessage]: ...
    def save_session_state(self, session_id: str, graph_name: str, shared_state: dict[str, Any]) -> None: ...
    def load_session_state(self, session_id: str) -> dict[str, Any]: ...


class CheckpointRepository(Protocol):
    def create_checkpoint(self, run_id: str, kind: str, payload: Any) -> int: ...
    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]: ...
    def load_latest_checkpoint(self, run_id: str) -> dict[str, Any] | None: ...
    def load_checkpoint(self, run_id: str, checkpoint_id: int) -> dict[str, Any] | None: ...


class HumanRequestRepository(Protocol):
    def create_human_request(
        self,
        run_id: str,
        request_key: str,
        kind: str,
        title: str,
        payload: dict[str, Any],
    ) -> HumanRequest: ...
    def list_human_requests(
        self,
        status: HumanRequestStatus | None = None,
        run_id: str | None = None,
    ) -> list[HumanRequest]: ...
    def resolve_human_request(
        self,
        request_id: str,
        *,
        status: HumanRequestStatus,
        response_payload: dict[str, Any] | None = None,
    ) -> HumanRequest: ...


class TraceRepository(Protocol):
    def record_event(
        self,
        run_id: str,
        kind: str,
        payload: Any,
        *,
        scope: str = 'runtime',
        node_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> dict[str, Any]: ...
    def load_trace(self, run_id: str) -> dict[str, Any]: ...
    def load_trace_tree(self, run_id: str) -> dict[str, Any]: ...


class WorkbenchRepository(Protocol):
    def list_workbench_sessions(self, owner_run_id: str | None = None) -> list[dict[str, Any]]: ...
    def load_workbench_session(self, session_id: str) -> dict[str, Any]: ...


class FederationRepository(Protocol):
    def list_federated_tasks(self) -> list[dict[str, Any]]: ...
    def list_federated_task_events(self, task_id: str, after_sequence: int = 0) -> list[dict[str, Any]]: ...
    def list_federated_subscriptions(self, task_id: str) -> list[dict[str, Any]]: ...
