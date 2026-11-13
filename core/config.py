"""Validated configuration. Credentials never enter the public run snapshot."""

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Provider = Literal["gemini", "openai", "gpu"]
ROLES = ("coordinator", "visual", "knowledge", "generation", "aggregator", "judge")


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProviderConfig(StrictConfig):
    model: str = Field(min_length=1)
    api_key_env: str
    base_url_env: str | None = None
    supports_images: bool = True
    supports_json: bool = True


class RoleConfig(StrictConfig):
    provider: Provider = "gemini"
    model: str | None = None
    api_key_env: str | None = None
    max_output_tokens: int | None = Field(default=None, ge=128, le=16384)
    thinking_level: Literal["minimal", "low", "medium", "high"] | None = None


class BudgetConfig(StrictConfig):
    max_llm_calls: int = Field(default=12, ge=1, le=100)
    deadline_seconds: float = Field(default=120, gt=0, le=600)
    request_timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_output_tokens: int = Field(default=2048, ge=128, le=16384)
    transient_retries: int = Field(default=1, ge=0, le=2)
    truncation_retries: int = Field(default=1, ge=0, le=1)
    max_output_tokens_ceiling: int = Field(default=8192, ge=128, le=16384)


class AppConfig(StrictConfig):
    schema_version: Literal[1] = 1
    workflow_version: str = "langgraph-v1"
    providers: dict[Provider, ProviderConfig] = Field(
        default_factory=lambda: {
            "gemini": ProviderConfig(model="gemini-3.8-flash", api_key_env="GEMINI_API_KEY"),
            "openai": ProviderConfig(
                model="gpt-4o-mini", api_key_env="OPENAI_API_KEY", base_url_env="OPENAI_BASE_URL"
            ),
            "gpu": ProviderConfig(
                model="local-vlm",
                api_key_env="LOCAL_INFERENCE_API_KEY",
                base_url_env="LOCAL_INFERENCE_URL",
            ),
        }
    )
    roles: dict[str, RoleConfig] = Field(
        default_factory=lambda: {role: RoleConfig() for role in ROLES}
    )
    fallback_providers: list[Provider] = Field(default_factory=list)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    parallel_workers: int = Field(default=3, ge=1, le=6)
    enable_generation: bool = False
    max_image_bytes: int = Field(default=10_000_000, ge=1)
    max_image_pixels: int = Field(default=20_000_000, ge=1)

    @model_validator(mode="after")
    def references(self):
        if set(self.roles) != set(ROLES):
            raise ValueError(f"roles must contain exactly {ROLES}")
        for name, role in self.roles.items():
            if role.provider not in self.providers:
                raise ValueError(f"Unknown provider: {role.provider}")
            provider = self.providers[role.provider]
            if name in {"coordinator", "visual", "judge"} and not provider.supports_images:
                raise ValueError(f"Role {name} requires image support")
            if name in {"coordinator", "judge"} and not provider.supports_json:
                raise ValueError(f"Role {name} requires JSON support")
        for provider in self.fallback_providers:
            if provider not in self.providers:
                raise ValueError(f"Unknown fallback: {provider}")
        return self

    def snapshot(self) -> dict:
        data = self.model_dump(mode="json")
        data["config_hash"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        return data


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(
        path
        or os.getenv("HERITAGE_CONFIG", "")
        or Path(__file__).resolve().parents[1] / "config/default.yaml"
    )
    overrides = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(overrides, dict):
        raise ValueError("Configuration must be a YAML object")

    def merge(base, update):
        for key, value in update.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                merge(base[key], value)
            else:
                base[key] = value
        return base

    data = merge(AppConfig().model_dump(mode="json"), overrides)
    # Explicit env overrides retain compatibility without guessing key prefixes.
    data.setdefault("providers", {})
    for provider, env_name in (("gemini", "GEMINI_MODEL"), ("openai", "OPENAI_MODEL")):
        if os.getenv(env_name):
            data["providers"].setdefault(provider, {})["model"] = os.environ[env_name]
    for role in ROLES:
        binding = data.setdefault("roles", {}).setdefault(role, {})
        for field, suffix in (("provider", "PROVIDER"), ("model", "MODEL")):
            if os.getenv(f"{role.upper()}_{suffix}"):
                binding[field] = os.environ[f"{role.upper()}_{suffix}"]
        if os.getenv(f"{role.upper()}_API_KEY"):
            binding["api_key_env"] = f"{role.upper()}_API_KEY"
    return AppConfig.model_validate(data)
