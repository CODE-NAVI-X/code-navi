"""Host composition layer over the kernel's single execution loop."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias
from uuid import uuid4

from kernel.core import (
    ContentBlock,
    ContextPolicy,
    KernelConfig,
    Message,
    PermissionGrant,
    Provider,
    ToolDispatcher,
    ToolExecutionContext,
    ToolRegistry,
    run,
)

from .agent import AgentSpec, RuntimeRequest, RuntimeResult
from .sessions import save_runtime_events, session_log_path

DispatcherFactory: TypeAlias = Callable[[str, tuple[str, ...]], ToolDispatcher]


def _text_from_message(message: Message | None) -> str | None:
    if message is None or message.role != "assistant":
        return None
    text = "".join(
        block.data["text"]
        for block in message.content
        if block.type == "text" and isinstance(block.data.get("text"), str)
    )
    return text or None


def _empty_dispatcher(run_id: str) -> ToolDispatcher:
    registry = ToolRegistry()
    registry.freeze()
    return registry.bind(
        PermissionGrant(run_scope=run_id),
        ToolExecutionContext(run_scope=run_id),
    )


class AgentRuntime:
    """Run one declared agent through the existing kernel loop."""

    def __init__(
        self,
        provider: Provider,
        *,
        dispatcher_factory: DispatcherFactory | None = None,
        context_policy: ContextPolicy | None = None,
        context_budget_tokens: int | None = None,
        session_dir: str | Path | None = None,
        default_config: KernelConfig | None = None,
    ) -> None:
        if not callable(getattr(provider, "complete", None)):
            raise TypeError("provider must implement complete()")
        if dispatcher_factory is not None and not callable(dispatcher_factory):
            raise TypeError("dispatcher_factory must be callable or None")
        if context_policy is not None and not callable(getattr(context_policy, "view", None)):
            raise TypeError("context_policy must implement view() or be None")
        if context_budget_tokens is not None and (
            not isinstance(context_budget_tokens, int)
            or isinstance(context_budget_tokens, bool)
            or context_budget_tokens < 1
        ):
            raise ValueError("context_budget_tokens must be a positive int or None")
        if session_dir is not None and not isinstance(session_dir, (str, Path)):
            raise TypeError("session_dir must be a path or None")
        if default_config is not None and not isinstance(default_config, KernelConfig):
            raise TypeError("default_config must be KernelConfig or None")
        self._provider = provider
        self._dispatcher_factory = dispatcher_factory
        self._context_policy = context_policy
        self._context_budget_tokens = context_budget_tokens
        self._session_dir = None if session_dir is None else Path(session_dir)
        self._default_config = default_config

    def run(
        self,
        agent: AgentSpec,
        request: RuntimeRequest,
        *,
        config: KernelConfig | None = None,
        interrupt_check: Callable[[], bool] | None = None,
    ) -> RuntimeResult:
        if not isinstance(agent, AgentSpec):
            raise TypeError("agent must be AgentSpec")
        if not isinstance(request, RuntimeRequest):
            raise TypeError("request must be RuntimeRequest")
        if config is not None and not isinstance(config, KernelConfig):
            raise TypeError("config must be KernelConfig or None")
        if interrupt_check is not None and not callable(interrupt_check):
            raise TypeError("interrupt_check must be callable or None")

        run_id = request.run_id or str(uuid4())
        if self._session_dir is not None:
            session_log_path(self._session_dir, request.session_id, run_id)
        if agent.tool_names and self._dispatcher_factory is None:
            raise ValueError("dispatcher_factory is required when agent declares tools")
        dispatcher = (
            _empty_dispatcher(run_id)
            if self._dispatcher_factory is None
            else self._dispatcher_factory(run_id, agent.tool_names)
        )
        if not callable(getattr(dispatcher, "provider_tools", None)) or not callable(
            getattr(dispatcher, "dispatch", None)
        ):
            raise TypeError("dispatcher_factory must return ToolDispatcher")
        provider_tools = tuple(dispatcher.provider_tools())
        if tuple(tool.name for tool in provider_tools) != agent.tool_names:
            raise ValueError("dispatcher provider_tools() names and order must match tool_names")

        system_metadata: dict[str, object] = {
            "agent_name": agent.name,
            "output_format": agent.output_format,
        }
        if request.session_id is not None:
            system_metadata["session_id"] = request.session_id
        initial_messages = (
            Message(
                "system",
                (ContentBlock("text", {"text": agent.system_prompt}),),
                system_metadata,
                pinned=True,
            ),
            *request.conversation_history,
            Message(
                "user",
                (ContentBlock("text", {"text": request.user_input}),),
                request.metadata,
                pinned=True,
            ),
        )
        effective_config = config or agent.default_config or self._default_config or KernelConfig()
        run_result = run(
            self._provider,
            dispatcher,
            initial_messages,
            effective_config,
            run_id=run_id,
            context_policy=self._context_policy,
            context_budget_tokens=self._context_budget_tokens,
            interrupt_check=interrupt_check,
        )
        final_messages = tuple(run_result.state.messages)
        output_text = _text_from_message(run_result.output)
        if output_text is None:
            for message in reversed(final_messages):
                output_text = _text_from_message(message)
                if output_text is not None:
                    break
        event_log_path = None
        if self._session_dir is not None:
            event_log_path = save_runtime_events(
                self._session_dir,
                request.session_id,
                run_id,
                run_result.events,
            )
        return RuntimeResult(
            agent.name,
            run_id,
            request.session_id,
            run_result,
            run_result.events,
            final_messages,
            output_text,
            event_log_path,
        )
