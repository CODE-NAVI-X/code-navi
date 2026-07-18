import json

import pytest

from kernel.core import ProviderCapabilities, ProviderTool


def test_provider_tool_json_round_trip() -> None:
    tool = ProviderTool(
        "lookup",
        "Look up a local value.",
        {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    )

    encoded = json.loads(json.dumps(tool.to_json()))
    encoded["args_schema"]["properties"]["q"]["type"] = "integer"

    assert tool.args_schema["properties"]["q"]["type"] == "string"
    assert ProviderTool.from_json(tool.to_json()) == tool


def test_provider_capabilities_json_round_trip() -> None:
    capabilities = ProviderCapabilities(
        supports_streaming=True,
        supports_parallel_tool_calls=True,
        max_context=128_000,
        unsupported_content_blocks=frozenset({"artifact_ref"}),
    )

    encoded = json.loads(json.dumps(capabilities.to_json()))

    assert ProviderCapabilities.from_json(encoded) == capabilities


def test_provider_tool_rejects_non_object_or_non_json_schema() -> None:
    with pytest.raises(ValueError, match="root"):
        ProviderTool("lookup", "Lookup.", {"type": "string"})
    with pytest.raises(TypeError, match="JSON-serializable"):
        ProviderTool("lookup", "Lookup.", {"type": "object", "bad": object()})
