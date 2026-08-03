"""Public schemas for research model configuration visibility."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class ConfigureProviderRequest(BaseModel):
    """One local-only provider configuration request; the secret is never returned."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["deepseek", "openai"]
    api_key: SecretStr
    model: str | None = Field(default=None, max_length=100)
    base_url: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_provider_fields(self) -> ConfigureProviderRequest:
        if self.provider == "openai" and not (self.model and self.model.strip()):
            raise ValueError("OpenAI 配置必须填写模型名称。")
        if self.base_url:
            normalized = self.base_url.strip().lower()
            if not normalized.startswith("https://"):
                raise ValueError("Base URL 必须使用 https://。")
        return self


class ProviderStatusResponse(BaseModel):
    """Secret-free view of the currently selected research provider."""

    schema_version: Literal["research-provider.v1"] = "research-provider.v1"
    provider: str
    model: str | None
    configured: bool
    mode: Literal["model", "rules"]
    configuration_method: Literal["local_file", "server_environment"]
    configuration_issue: Literal["invalid_api_key", "missing_model"] | None = None


class ProviderConnectionTestResponse(BaseModel):
    """Result of one explicit, no-tool model connection test."""

    schema_version: Literal["research-provider-test.v1"] = "research-provider-test.v1"
    connected: bool
    provider: str
    model: str | None
    latency_ms: int = Field(ge=0)
    message: str
    run_id: str | None = None
    failure_code: Literal[
        "invalid_credentials",
        "model_unavailable",
        "timeout",
        "network_error",
        "invalid_response",
        "provider_error",
    ] | None = None
