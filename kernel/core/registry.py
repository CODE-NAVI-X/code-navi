"""Explicit S4 tool registry, validation, and per-run permissions."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator

from .types import ToolCall, ToolPermission, ToolResult

ToolHandler = Callable[[Mapping[str, Any], "ToolExecutionContext"], Any]
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_EXPLICIT_PERMISSIONS = frozenset(ToolPermission) - {ToolPermission.READ}


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _roots(values: tuple[Path | str, ...]) -> tuple[Path, ...]:
    return tuple(Path(value).expanduser().resolve(strict=False) for value in values)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Trusted, host-registered definition of a model-callable tool."""

    name: str
    description: str
    args_schema: Mapping[str, Any]
    required_permissions: frozenset[ToolPermission]
    workspace_path_args: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.name):
            raise ValueError("invalid tool name")
        if not self.description.strip():
            raise ValueError("tool description is required")
        schema = _json_copy(dict(self.args_schema))
        if schema.get("type") != "object":
            raise ValueError("tool args schema root must have type 'object'")
        permissions = frozenset(ToolPermission(item) for item in self.required_permissions)
        if not permissions:
            raise ValueError("tool requires at least one permission")
        paths = tuple(self.workspace_path_args)
        if ToolPermission.WRITE in permissions and not paths:
            raise ValueError("WRITE tools must declare workspace_path_args")
        if any(not path or "." in path for path in paths):
            raise ValueError("workspace_path_args must be top-level property names")
        properties = schema.get("properties", {})
        required = set(schema.get("required", ()))
        if any(path not in properties or path not in required for path in paths):
            raise ValueError(
                "workspace path arguments must be declared required schema properties"
            )
        object.__setattr__(self, "args_schema", schema)
        object.__setattr__(self, "required_permissions", permissions)
        object.__setattr__(self, "workspace_path_args", paths)


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    """Authorization value created for exactly one run by a host."""

    run_scope: str
    allowed_permissions: frozenset[ToolPermission] = field(
        default_factory=lambda: frozenset({ToolPermission.READ})
    )
    workspace_roots: tuple[Path | str, ...] = ()
    destructive_tool_names: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.run_scope:
            raise ValueError("PermissionGrant run_scope is required")
        permissions = frozenset(ToolPermission(item) for item in self.allowed_permissions)
        permissions |= {ToolPermission.READ}
        object.__setattr__(self, "allowed_permissions", permissions)
        object.__setattr__(self, "workspace_roots", _roots(tuple(self.workspace_roots)))
        object.__setattr__(
            self, "destructive_tool_names", frozenset(self.destructive_tool_names)
        )


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """Trusted, minimal capabilities made available to handlers for one run."""

    run_scope: str
    workspace_roots: tuple[Path | str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    executables: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.run_scope:
            raise ValueError("ToolExecutionContext run_scope is required")
        object.__setattr__(self, "workspace_roots", _roots(tuple(self.workspace_roots)))
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))
        object.__setattr__(self, "executables", MappingProxyType(dict(self.executables)))


class ToolUserError(Exception):
    """Expected, safe-to-report handler failure."""


@dataclass(frozen=True, slots=True)
class _Entry:
    spec: ToolSpec
    handler: ToolHandler
    validator: Draft202012Validator


class ToolRegistry:
    """Long-lived explicit tool definitions; never stores a permission grant."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._frozen = False

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        if self._frozen:
            raise RuntimeError("tool registry is frozen")
        if spec.name in self._entries:
            raise ValueError(f"tool already registered: {spec.name}")
        schema = _json_copy(spec.args_schema)
        Draft202012Validator.check_schema(schema)
        private_spec = ToolSpec(
            spec.name,
            spec.description,
            schema,
            spec.required_permissions,
            spec.workspace_path_args,
        )
        self._entries[spec.name] = _Entry(
            private_spec, handler, Draft202012Validator(schema)
        )

    def freeze(self) -> None:
        self._frozen = True

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(
            ToolSpec(
                entry.spec.name,
                entry.spec.description,
                entry.spec.args_schema,
                entry.spec.required_permissions,
                entry.spec.workspace_path_args,
            )
            for entry in self._entries.values()
        )

    def bind(
        self, grant: PermissionGrant, context: ToolExecutionContext
    ) -> "RunToolDispatcher":
        if grant.run_scope != context.run_scope:
            raise ValueError("grant and execution context must belong to the same run")
        if grant.workspace_roots != context.workspace_roots:
            raise ValueError("grant and execution context workspace roots must match")
        return RunToolDispatcher(MappingProxyType(self._entries.copy()), grant, context)


class RunToolDispatcher:
    """Short-lived dispatcher bound to one run's grant and capabilities."""

    def __init__(
        self,
        entries: Mapping[str, _Entry],
        grant: PermissionGrant,
        context: ToolExecutionContext,
    ) -> None:
        self._entries = entries
        self._grant = grant
        self._context = context

    def dispatch(self, call: ToolCall) -> ToolResult:
        entry = self._entries.get(call.name)
        if entry is None:
            return self._failure(call, "unknown_tool", "tool is not registered")

        errors = sorted(entry.validator.iter_errors(call.args), key=lambda item: list(item.path))
        if errors:
            details = [
                {
                    "path": "$" + "".join(f"[{part!r}]" for part in error.path),
                    "keyword": error.validator,
                    "message": error.message,
                }
                for error in errors[:8]
            ]
            return self._failure(
                call, "invalid_arguments", "tool arguments failed schema validation",
                entry.spec.required_permissions, {"validation_errors": details}
            )

        denial = self._permission_denial(entry.spec, call.args)
        if denial is not None:
            return self._failure(
                call, "permission_denied", "tool is not authorized for this run",
                entry.spec.required_permissions, denial
            )

        audit = self._audit(entry.spec, "allowed")
        try:
            raw_value = entry.handler(_json_copy(call.args), self._context)
        except ToolUserError as exc:
            return self._failure(
                call, "tool_error", str(exc), entry.spec.required_permissions
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            return self._failure(
                call, "tool_internal_error", "tool execution failed",
                entry.spec.required_permissions
            )
        try:
            value = _json_copy(raw_value)
        except (TypeError, ValueError):
            return self._failure(
                call, "invalid_tool_output", "tool returned a non-JSON value",
                entry.spec.required_permissions
            )
        return ToolResult(
            call.id, call.name, {"ok": True, "value": value, "audit": audit},
            permissions=entry.spec.required_permissions
        )

    def _permission_denial(
        self, spec: ToolSpec, args: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        missing = sorted(
            permission.value
            for permission in spec.required_permissions & _EXPLICIT_PERMISSIONS
            if permission not in self._grant.allowed_permissions
        )
        destructive_missing = (
            ToolPermission.DESTRUCTIVE in spec.required_permissions
            and spec.name not in self._grant.destructive_tool_names
        )
        scope_errors = self._scope_errors(spec, args)
        if not missing and not destructive_missing and not scope_errors:
            return None
        return {
            "required_permissions": sorted(p.value for p in spec.required_permissions),
            "missing_permissions": missing,
            "destructive_tool_grant_missing": destructive_missing,
            "scope_errors": scope_errors,
        }

    def _scope_errors(
        self, spec: ToolSpec, args: Mapping[str, Any]
    ) -> list[dict[str, str]]:
        if ToolPermission.WRITE not in spec.required_permissions:
            return []
        errors: list[dict[str, str]] = []
        for key in spec.workspace_path_args:
            value = args.get(key)
            if not isinstance(value, str) or not value or "\x00" in value:
                errors.append({"argument": key, "reason": "invalid_workspace_path"})
                continue
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                if len(self._grant.workspace_roots) != 1:
                    errors.append({"argument": key, "reason": "ambiguous_workspace_root"})
                    continue
                candidate = self._grant.workspace_roots[0] / candidate
            resolved = candidate.resolve(strict=False)
            if not any(_within(resolved, root) for root in self._grant.workspace_roots):
                errors.append({"argument": key, "reason": "outside_workspace"})
        return errors

    @staticmethod
    def _audit(spec: ToolSpec, decision: str) -> dict[str, Any]:
        return {
            "grant_check": decision,
            "required_permissions": sorted(p.value for p in spec.required_permissions),
        }

    @classmethod
    def _failure(
        cls,
        call: ToolCall,
        code: str,
        message: str,
        permissions: frozenset[ToolPermission] = frozenset(),
        details: Mapping[str, Any] | None = None,
    ) -> ToolResult:
        error = {
            "code": code,
            "message": message,
            "details": dict(details or {}),
            "retryable": code
            in {"unknown_tool", "invalid_arguments", "permission_denied", "tool_error"},
        }
        result = {"ok": False, "error": error, "audit": {
            "grant_check": "denied" if code == "permission_denied" else "not_reached"
        }}
        return ToolResult(
            call.id, call.name, result, f"{code}: {message}", permissions
        )


def _within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath(
            (os.path.normcase(path), os.path.normcase(root))
        ) == os.path.normcase(root)
    except ValueError:
        return False
