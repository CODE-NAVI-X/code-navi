from pathlib import Path

import pytest

from kernel.core import (
    ContentBlock,
    KernelConfig,
    Message,
    MockProvider,
    PermissionGrant,
    ProviderResult,
    RunStatus,
    ToolCall,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
    ToolSpec,
    run,
)


def spec_for(
    name: str,
    permissions: set[ToolPermission],
    *,
    workspace_path_args: tuple[str, ...] = (),
) -> ToolSpec:
    properties = {key: {"type": "string"} for key in workspace_path_args}
    return ToolSpec(
        name,
        f"Exercise {name} permissions.",
        {
            "type": "object",
            "properties": properties,
            "required": list(workspace_path_args),
            "additionalProperties": False,
        },
        frozenset(permissions),
        workspace_path_args,
    )


def dispatcher(
    registry: ToolRegistry,
    scope: str,
    *,
    permissions: set[ToolPermission] | None = None,
    roots: tuple[Path, ...] = (),
    destructive_names: set[str] | None = None,
):
    grant = PermissionGrant(
        scope,
        frozenset(permissions or {ToolPermission.READ}),
        roots,
        frozenset(destructive_names or set()),
    )
    return registry.bind(grant, ToolExecutionContext(scope, roots))


def code(result) -> str:
    return result.result["error"]["code"]


def test_read_is_the_only_default_allowed_permission() -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(
        spec_for("read_local", {ToolPermission.READ}),
        lambda args, context: calls.append("read") or "ok",
    )

    result = dispatcher(registry, "read-run").dispatch(
        ToolCall("tc-read", "read_local", {})
    )

    assert result.result["ok"] is True
    assert calls == ["read"]


@pytest.mark.parametrize(
    "permission",
    [
        ToolPermission.EXECUTE,
        ToolPermission.NETWORK,
        ToolPermission.SENSITIVE,
        ToolPermission.PUBLISH,
    ],
)
def test_non_read_permissions_are_deny_by_default(permission: ToolPermission) -> None:
    calls: list[str] = []
    name = f"needs_{permission.value.lower()}"
    registry = ToolRegistry()
    registry.register(
        spec_for(name, {permission}),
        lambda args, context: calls.append("called") or "ok",
    )

    denied = dispatcher(registry, "denied").dispatch(ToolCall("tc-1", name, {}))
    allowed = dispatcher(
        registry, "allowed", permissions={permission}
    ).dispatch(ToolCall("tc-2", name, {}))

    assert code(denied) == "permission_denied"
    assert permission.value in denied.result["error"]["details"]["missing_permissions"]
    assert allowed.result["ok"] is True
    assert calls == ["called"]


def test_composed_permissions_require_all_flags() -> None:
    registry = ToolRegistry()
    registry.register(
        spec_for(
            "remote_private_read",
            {ToolPermission.READ, ToolPermission.NETWORK, ToolPermission.SENSITIVE},
        ),
        lambda args, context: "secret",
    )

    result = dispatcher(
        registry, "partial", permissions={ToolPermission.NETWORK}
    ).dispatch(ToolCall("tc-1", "remote_private_read", {}))

    assert code(result) == "permission_denied"
    assert result.result["error"]["details"]["missing_permissions"] == ["SENSITIVE"]


def test_destructive_requires_flag_and_specific_tool_name() -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(
        spec_for("delete_file", {ToolPermission.DESTRUCTIVE}),
        lambda args, context: calls.append("deleted") or "ok",
    )

    no_flag = dispatcher(
        registry, "no-flag", destructive_names={"delete_file"}
    ).dispatch(ToolCall("tc-1", "delete_file", {}))
    no_name = dispatcher(
        registry, "no-name", permissions={ToolPermission.DESTRUCTIVE}
    ).dispatch(ToolCall("tc-2", "delete_file", {}))
    allowed = dispatcher(
        registry,
        "allowed",
        permissions={ToolPermission.DESTRUCTIVE},
        destructive_names={"delete_file"},
    ).dispatch(ToolCall("tc-3", "delete_file", {}))

    assert code(no_flag) == code(no_name) == "permission_denied"
    assert no_name.result["error"]["details"]["destructive_tool_grant_missing"]
    assert allowed.result["ok"] is True
    assert calls == ["deleted"]


def test_grant_does_not_leak_through_long_lived_registry() -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(
        spec_for("execute", {ToolPermission.EXECUTE}),
        lambda args, context: calls.append(context.run_scope) or "ok",
    )

    first = dispatcher(
        registry, "run-one", permissions={ToolPermission.EXECUTE}
    ).dispatch(ToolCall("tc-1", "execute", {}))
    second = dispatcher(registry, "run-two").dispatch(
        ToolCall("tc-2", "execute", {})
    )

    assert first.result["ok"] is True
    assert code(second) == "permission_denied"
    assert calls == ["run-one"]


def test_grant_and_context_cannot_be_bound_across_run_scopes() -> None:
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="same run"):
        registry.bind(PermissionGrant("run-one"), ToolExecutionContext("run-two"))


def test_write_is_allowed_only_inside_workspace(tmp_path: Path) -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(
        spec_for("write_new_file", {ToolPermission.WRITE}, workspace_path_args=("path",)),
        lambda args, context: calls.append(args["path"]) or "ok",
    )
    bound = dispatcher(
        registry,
        "write-run",
        permissions={ToolPermission.WRITE},
        roots=(tmp_path,),
    )

    inside = bound.dispatch(ToolCall("tc-1", "write_new_file", {"path": "new.txt"}))
    outside = bound.dispatch(
        ToolCall("tc-2", "write_new_file", {"path": str(tmp_path.parent / "escape.txt")})
    )
    traversal = bound.dispatch(
        ToolCall("tc-3", "write_new_file", {"path": "../escape.txt"})
    )

    assert inside.result["ok"] is True
    assert code(outside) == code(traversal) == "permission_denied"
    assert calls == ["new.txt"]


def test_write_is_denied_without_explicit_flag_even_inside_workspace(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(
        spec_for(
            "write_new_file",
            {ToolPermission.WRITE},
            workspace_path_args=("path",),
        ),
        lambda args, context: calls.append(args["path"]) or "ok",
    )

    result = dispatcher(registry, "write-denied", roots=(tmp_path,)).dispatch(
        ToolCall("tc-1", "write_new_file", {"path": "inside.txt"})
    )

    assert code(result) == "permission_denied"
    assert result.result["error"]["details"]["missing_permissions"] == ["WRITE"]
    assert calls == []


def test_denial_is_tool_result_and_loop_continues_without_new_event_types() -> None:
    call = ToolCall("tc-1", "execute", {})
    tool_message = Message(
        "assistant", (ContentBlock("tool_use", {"tool_call": call.to_json()}),)
    )
    registry = ToolRegistry()
    registry.register(
        spec_for("execute", {ToolPermission.EXECUTE}), lambda args, context: "no"
    )
    result = run(
        MockProvider(
            [ProviderResult(tool_message), ProviderResult(Message("assistant"))]
        ),
        dispatcher(registry, "loop-run"),
        [Message("user")],
        KernelConfig(max_steps=3, max_tool_calls=2),
    )

    returned = next(event for event in result.events if event.type == "tool_returned")
    payload = returned.payload["tool_result"]
    assert result.status == RunStatus.COMPLETED
    assert payload["result"]["error"]["code"] == "permission_denied"
    assert payload["result"]["audit"]["grant_check"] == "denied"
    assert set(event.type for event in result.events) <= {
        "run_started",
        "message_added",
        "tool_called",
        "tool_returned",
        "budget_updated",
        "interrupted",
        "error",
        "run_finished",
    }
