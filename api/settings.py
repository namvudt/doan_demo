import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)
    environment: str = "development"
    database_url: SecretStr = SecretStr("sqlite:///data/api.sqlite")
    data_dir: Path = ROOT / "data"
    embedded_worker: bool = True
    model_mode: str = "live"
    bootstrap_token: SecretStr = SecretStr("")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    session_ttl_seconds: int = Field(default=604800, ge=60)
    max_active_per_owner: int = Field(default=3, ge=1)
    max_runs_per_day: int = Field(default=100, ge=1)
    max_pending_runs: int = Field(default=100, ge=1)
    max_sessions: int = Field(default=1000, ge=1)
    max_assets_per_owner: int = Field(default=100, ge=1)
    max_upload_bytes: int = Field(default=10_000_000, ge=1024)
    poll_seconds: float = Field(default=0.25, gt=0)
    heartbeat_seconds: float = Field(default=5, gt=0)
    lease_seconds: float = Field(default=45, ge=1)
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_dir: Path | None = None
    log_max_bytes: int = Field(default=10_000_000, ge=1024)
    log_backups: int = Field(default=5, ge=1, le=100)
    operations_token: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def validate_runtime(self):
        if self.environment not in {"development", "production"}:
            raise ValueError("API_ENV must be development or production")
        if self.model_mode not in {"live", "demo"}:
            raise ValueError("API_MODEL_MODE must be live or demo")
        if self.environment == "production" and len(self.bootstrap_token.get_secret_value()) < 32:
            raise ValueError("Production requires API_BOOTSTRAP_TOKEN with at least 32 characters")
        if self.environment == "production" and not self.database_url.get_secret_value().startswith(
            "postgresql"
        ):
            raise ValueError("Production requires a PostgreSQL DATABASE_URL")
        if self.heartbeat_seconds >= self.lease_seconds / 2:
            raise ValueError("Heartbeat must be shorter than half of the worker lease")
        if (
            self.operations_token.get_secret_value()
            and len(self.operations_token.get_secret_value()) < 32
        ):
            raise ValueError("API_OPERATIONS_TOKEN requires at least 32 characters")
        if "*" in self.cors_origins:
            raise ValueError("List explicit frontend origins")
        return self

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        fields = {
            "environment": "API_ENV",
            "database_url": "DATABASE_URL",
            "data_dir": "API_DATA_DIR",
            "embedded_worker": "API_EMBEDDED_WORKER",
            "model_mode": "API_MODEL_MODE",
            "bootstrap_token": "API_BOOTSTRAP_TOKEN",
            "session_ttl_seconds": "API_SESSION_TTL_SECONDS",
            "max_active_per_owner": "API_MAX_ACTIVE_PER_OWNER",
            "max_runs_per_day": "API_MAX_RUNS_PER_DAY",
            "max_pending_runs": "API_MAX_PENDING_RUNS",
            "max_upload_bytes": "API_MAX_UPLOAD_BYTES",
            "log_level": "API_LOG_LEVEL",
            "log_dir": "API_LOG_DIR",
            "log_max_bytes": "API_LOG_MAX_BYTES",
            "log_backups": "API_LOG_BACKUPS",
            "operations_token": "API_OPERATIONS_TOKEN",
            "heartbeat_seconds": "API_HEARTBEAT_SECONDS",
            "lease_seconds": "API_LEASE_SECONDS",
        }
        values = {field: os.environ[key] for field, key in fields.items() if key in os.environ}
        if os.getenv("API_CORS_ORIGINS"):
            values["cors_origins"] = [
                s.strip() for s in os.environ["API_CORS_ORIGINS"].split(",") if s.strip()
            ]
        try:
            return cls(**values)
        except ValidationError:
            raise ValueError(
                "Invalid API settings; check environment, database driver, mode and required production secrets"
            ) from None
