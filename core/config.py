"""Validated configuration. Credentials never enter the public run snapshot."""

import hashlib
import json
import os
import re
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
    json_schema_mode: Literal["full", "compact"] = "full"


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


class ImagePolicy(StrictConfig):
    ocr_enabled: bool = True
    ocr_role: str = "visual"
    max_regions: int = Field(default=3, ge=0, le=8)
    max_ocr_calls: int = Field(default=2, ge=0, le=8)
    min_short_side: int = Field(default=320, ge=32)
    dark_threshold: float = Field(default=45, ge=0, le=255)
    low_contrast_threshold: float = Field(default=20, ge=0, le=128)
    preprocess: Literal["none", "autocontrast"] = "autocontrast"


class RetrievalPolicy(StrictConfig):
    wikipedia_enabled: bool = True
    corpus_path: str = "data/heritage/corpus.jsonl"
    max_results: int = Field(default=4, ge=1, le=8)
    candidate_limit: int = Field(default=6, ge=1, le=12)
    entity_first: bool = True
    require_entity_mention: bool = True
    relation_aware: bool = True
    require_relation_coverage: bool = True
    relation_rules: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    max_http_requests: int = Field(default=24, ge=1, le=80)
    max_queries: int = Field(default=2, ge=1, le=4)
    max_source_chars: int = Field(default=2400, ge=200, le=8000)
    timeout_seconds: float = Field(default=6, gt=0, le=30)
    max_document_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    max_redirects: int = Field(default=2, ge=0, le=4)
    allowed_domains: list[str] = Field(
        default_factory=lambda: [
            "vi.wikipedia.org",
            "vanmieu.gov.vn",
            "hoangthanhthanglong.vn",
            "hanoi.gov.vn",
        ]
    )

    @model_validator(mode="after")
    def valid_relation_patterns(self):
        for rule in self.relation_rules.values():
            for pattern in rule.get("coverage_patterns", []):
                try:
                    re.compile(pattern)
                except re.error:
                    raise ValueError("Invalid retrieval coverage pattern") from None
        return self


class ClaimPolicy(StrictConfig):
    allow_han_nom_reading: bool = False
    require_source_for_specific_materials: bool = True
    require_source_for_dates: bool = True
    require_relation_quote: bool = True
    source_relation_rules: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    specific_material_terms: list[str] = Field(
        default_factory=lambda: [
            "gỗ lim",
            "gỗ mít",
            "gỗ sến",
            "gỗ táu",
            "gỗ nghiến",
            "gỗ mun",
            "đồng thau",
            "hợp kim",
            "đá vôi",
            "đá bazan",
            "đá granit",
            "đá hoa cương",
            "đá cẩm thạch",
            "đá xanh",
            "gạch Bát Tràng",
            "bronze",
            "brass",
            "limestone",
            "granite",
            "marble",
        ]
    )

    @model_validator(mode="after")
    def valid_source_patterns(self):
        for rule in self.source_relation_rules.values():
            for name, patterns in rule.items():
                if name.endswith("patterns"):
                    for pattern in patterns:
                        try:
                            re.compile(
                                pattern.replace("{subject}", "subject").replace(
                                    "{object}", "object"
                                )
                            )
                        except re.error:
                            raise ValueError("Invalid source relation pattern") from None
        return self


class RecognitionPolicy(StrictConfig):
    enabled: bool = True
    min_observations: int = Field(default=2, ge=1, le=20)
    max_status: Literal["probable", "recognized"] = "probable"
    max_disambiguation_rounds: int = Field(default=0, ge=0, le=1)


class QuestionPolicy(StrictConfig):
    nearest_patterns: list[str] = Field(
        default_factory=lambda: [r"\bgan\b[^.!?;\n]{0,80}\bnhat\b", r"\b(?:closest|nearest)\b"]
    )
    nearest_terms: list[str] = Field(default_factory=list)
    nearest_scope_terms: list[str] = Field(
        default_factory=lambda: [
            "trong số",
            "trong phạm vi",
            "trong bán kính",
            "among",
            "within",
            "listed",
        ]
    )
    require_nearest_scope: bool = True
    nearest_scope_max_chars: int = Field(default=500, ge=50, le=2000)

    @model_validator(mode="after")
    def valid_nearest_patterns(self):
        for pattern in self.nearest_patterns:
            try:
                re.compile(pattern)
            except re.error:
                raise ValueError("Invalid nearest question pattern") from None
        return self

    certainty_terms: list[str] = Field(
        default_factory=lambda: [
            "xác nhận chắc chắn",
            "khẳng định chắc chắn",
            "xác định tuyệt đối",
            "with certainty",
        ]
    )
    certainty_negations: list[str] = Field(
        default_factory=lambda: [
            "không cần",
            "không yêu cầu",
            "không nhất thiết",
            "chưa cần",
            "khỏi",
            "no need",
            "do not",
            "don't",
            "without",
        ]
    )
    unknown_answers: list[str] = Field(
        default_factory=lambda: [
            "không biết",
            "tôi không biết",
            "mình không biết",
            "em không biết",
            "không biết tên",
            "tôi không biết tên",
            "không rõ",
            "chưa rõ",
            "không chắc",
            "không chắc chắn",
            "I don't know",
            "unknown",
            "not sure",
        ]
    )
    split_history_slots: bool = True
    history_facets: dict[Literal["construction", "restoration", "reconstruction"], list[str]] = (
        Field(
            default_factory=lambda: {
                "construction": ["khởi dựng", "khởi công", "xây dựng khi nào", "năm xây dựng"],
                "restoration": ["trùng tu", "tu bổ"],
                "reconstruction": ["tái dựng", "xây lại", "phục dựng"],
            }
        )
    )
    facet_questions: dict[str, str] = Field(
        default_factory=lambda: {
            "construction": "Công trình được khởi dựng khi nào?",
            "restoration": "Những mốc trùng tu của công trình có tư liệu đối chiếu là gì?",
            "reconstruction": "Những mốc tái dựng của công trình có tư liệu đối chiếu là gì?",
        }
    )


class PerceptionPolicy(StrictConfig):
    separate_readability: bool = False
    ocr_only_when_requested: bool = False
    concise_claims: bool = False
    resolve_before_retrieval: bool = True
    require_count_grounding: bool = False
    reject_suspected_axis_swap: bool = True


class EntityPolicy(StrictConfig):
    reject_answer_values: bool = True
    allowed_candidate_types: list[str] = Field(
        default_factory=lambda: ["heritage_site", "place", "protected_area", "unknown"]
    )
    extract_explicit_subject: bool = True
    subject_patterns: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_subject_patterns(self):
        for pattern in self.subject_patterns:
            try:
                compiled = re.compile(pattern)
            except re.error:
                raise ValueError("Invalid subject extraction pattern") from None
            if "subject" not in compiled.groupindex:
                raise ValueError("Subject pattern requires a named subject group")
        return self


class AccuracyPolicy(StrictConfig):
    enabled: bool = False
    pilot_region: str = "Hà Nội"
    entity_catalog: str = "config/heritage/hanoi.entities.json"
    image: ImagePolicy = Field(default_factory=ImagePolicy)
    retrieval: RetrievalPolicy = Field(default_factory=RetrievalPolicy)
    claim_policy: ClaimPolicy = Field(default_factory=ClaimPolicy)
    recognition: RecognitionPolicy = Field(default_factory=RecognitionPolicy)
    questions: QuestionPolicy = Field(default_factory=QuestionPolicy)
    perception: PerceptionPolicy = Field(default_factory=PerceptionPolicy)
    entities: EntityPolicy = Field(default_factory=EntityPolicy)
    verifier_contract_retries: int = Field(default=1, ge=0, le=1)
    intermediate_max_chars: int = Field(default=1800, ge=300, le=8000)
    verifier_role: str = "judge"
    max_tool_calls: int = Field(default=12, ge=1, le=40)
    max_clarifications: int = Field(default=2, ge=0, le=4)
    clarification_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    max_conversation_llm_calls: int = Field(default=24, ge=1, le=100)
    min_quote_chars: int = Field(default=12, ge=1, le=100)
    max_claims: int = Field(default=20, ge=1, le=40)
    require_identity_agreement: bool = True
    max_recovery_rounds: int = Field(default=1, ge=0, le=1)


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
    accuracy: AccuracyPolicy = Field(default_factory=AccuracyPolicy)
    preflight_ttl_seconds: float = Field(default=300, ge=0, le=3600)
    preflight_timeout_seconds: float = Field(default=5, gt=0, le=30)
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
        accuracy_roles = ("visual", self.accuracy.verifier_role)
        if self.accuracy.image.ocr_enabled and self.accuracy.image.max_ocr_calls:
            accuracy_roles += (self.accuracy.image.ocr_role,)
        for role in accuracy_roles if self.accuracy.enabled else ():
            if role not in self.roles:
                raise ValueError("Accuracy roles must reference a configured role")
            provider = self.providers[self.roles[role].provider]
            if not provider.supports_images or not provider.supports_json:
                raise ValueError("Accuracy OCR/verifier require image and JSON support")
        return self

    def snapshot(self) -> dict:
        data = self.model_dump(mode="json")
        data["config_hash"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        return data


def config_validation_issues(error):
    """Project bounded field paths/error codes without validation inputs, context or messages."""
    schema = AppConfig.model_json_schema()
    known = {"config", "gemini", "openai", "gpu", *ROLES}
    for model in [schema, *schema.get("$defs", {}).values()]:
        known.update(model.get("properties", {}))
    issues = []
    for item in error.errors(include_input=False, include_context=False, include_url=False)[:8]:
        parts = [
            str(part) if isinstance(part, int) or part in known else "unknown_field"
            for part in item["loc"][:8]
        ]
        issues.append({"field": ".".join(parts) or "config", "code": item["type"]})
    return issues


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(
        path
        or os.getenv("HERITAGE_CONFIG", "")
        or Path(__file__).resolve().parents[1] / "config/default.yaml"
    )

    def merge(base, update):
        for key, value in update.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                merge(base[key], value)
            else:
                base[key] = value
        return base

    def read(path, seen=()):
        path = path.resolve()
        if path in seen or len(seen) >= 8:
            raise ValueError("Configuration inheritance cycle or excessive depth")
        overrides = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(overrides, dict):
            raise ValueError("Configuration must be a YAML object")
        parent = overrides.pop("extends", None)
        base = read(path.parent / parent, (*seen, path)) if parent else {}
        return merge(base, overrides)

    data = merge(AppConfig().model_dump(mode="json"), read(config_path))
    for env_name, field in (("HERITAGE_ACCURACY_ENABLED", "enabled"),):
        if env_name in os.environ:
            value = os.environ[env_name].strip().lower()
            if value not in {"true", "false"}:
                raise ValueError(f"{env_name} must be true or false")
            data.setdefault("accuracy", {})[field] = value == "true"
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
