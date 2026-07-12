from pathlib import Path

import pytest
from jsonschema.exceptions import SchemaError

from kernel.core import (
    PermissionGrant,
    ToolCall,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
    ToolSpec,
)


def read_spec(schema: dict | None = None) -> ToolSpec:
    return ToolSpec(
        "lookup",
        "Look up a local value.",
        schema
        or {
            "type": "object",
            "properties": {"q": {"type": "string", "minLength": 1}},
            "required": ["q"],
            "additionalProperties": False,
        },
        frozenset({ToolPermission.READ}),
    )


def bind(registry: ToolRegistry, scope: str = "run-1"):
    return registry.bind(PermissionGrant(scope), ToolExecutionContext(scope))


def error_code(result) -> str:
    return result.result["error"]["code"]


def test_explicit_registration_success_and_freeze() -> None:
    registry = ToolRegistry()
    registry.register(read_spec(), lambda args, context: {"answer": args["q"]})

    assert [spec.name for spec in registry.specs()] == ["lookup"]
    registry.freeze()
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register(
            ToolSpec(
                "other",
                "Another tool.",
                {"type": "object", "additionalProperties": False},
                frozenset({ToolPermission.READ}),
            ),
            lambda args, context: None,
        )


def test_duplicate_registration_is_rejected() -> None:
    registry = ToolRegistry()
    registry.register(read_spec(), lambda args, context: None)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(read_spec(), lambda args, context: None)


def test_schema_itself_is_checked_at_registration() -> None:
    registry = ToolRegistry()
    malformed = read_spec(
        {
            "type": "object",
            "properties": {"q": {"type": "not-a-json-schema-type"}},
        }
    )

    with pytest.raises(SchemaError):
        registry.register(malformed, lambda args, context: None)


def test_write_spec_requires_a_required_workspace_path_property() -> None:
    with pytest.raises(ValueError, match="required schema properties"):
        ToolSpec(
            "write_file",
            "Write a new file.",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "additionalProperties": False,
            },
            frozenset({ToolPermission.WRITE}),
            ("path",),
        )


def test_unknown_tool_returns_structured_error_without_handler() -> None:
    registry = ToolRegistry()
    calls: list[dict] = []
    registry.register(read_spec(), lambda args, context: calls.append(dict(args)))

    result = bind(registry).dispatch(ToolCall("tc-1", "missing", {}))

    assert error_code(result) == "unknown_tool"
    assert result.error == "unknown_tool: tool is not registered"
    assert result.result["ok"] is False
    assert calls == []


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"q": ""},
        {"q": 1},
        {"q": None},
        {"q": "ok", "unexpected": True},
        {"q": ["not", "a", "string"]},
    ],
)
def test_invalid_arguments_never_reach_handler(args: dict) -> None:
    calls: list[dict] = []
    registry = ToolRegistry()
    registry.register(read_spec(), lambda value, context: calls.append(dict(value)))

    result = bind(registry).dispatch(ToolCall("tc-1", "lookup", args))

    assert error_code(result) == "invalid_arguments"
    assert result.result["error"]["details"]["validation_errors"]
    assert calls == []


def test_valid_arguments_reach_handler_as_a_copy() -> None:
    seen: list[dict] = []
    registry = ToolRegistry()

    def handler(args, context):
        seen.append(dict(args))
        args["q"] = "mutated"
        return {"answer": "ok"}

    registry.register(read_spec(), handler)
    call = ToolCall("tc-1", "lookup", {"q": "original"})

    result = bind(registry).dispatch(call)

    assert result.result["ok"] is True
    assert result.result["value"] == {"answer": "ok"}
    assert result.result["audit"]["grant_check"] == "allowed"
    assert call.args == {"q": "original"}
    assert seen == [{"q": "original"}]


def test_non_json_handler_output_is_normalized() -> None:
    registry = ToolRegistry()
    registry.register(read_spec(), lambda args, context: Path("not-json"))

    result = bind(registry).dispatch(ToolCall("tc-1", "lookup", {"q": "x"}))

    assert error_code(result) == "invalid_tool_output"
