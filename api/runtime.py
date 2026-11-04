import hashlib
import os
import time
from contextlib import nullcontext
from io import BytesIO
from uuid import uuid4

from alembic import command
from alembic.config import Config
from langsmith import tracing_context
from PIL import Image
from sqlalchemy import func, select, text, update

from api.database import Database
from api.demo import DemoManager, DemoSearch
from api.models import Asset, Run, SessionToken
from api.settings import ROOT
from api.store import Store, StoreError, owned
from core.config import AppConfig, load_config
from core.gateway import LLMManager
from core.images import validate_image
from workflow.service import RunService


class Runtime:
    def __init__(self, settings, *, manager_factory=None):
        self.settings = settings
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.data_dir / "assets").mkdir(exist_ok=True)
        self.db = Database(settings.database_url.get_secret_value())
        self.store = Store(self.db, settings)
        self.manager_factory = manager_factory

    def migrate(self):
        cfg = Config(str(ROOT / "alembic.ini"))
        with self.db.engine.begin() as connection:
            if self.db.engine.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(714802003)"))
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")

    def config(self):
        return load_config()

    def manager(self, config=None, mode=None):
        config = config or self.config()
        mode = mode or self.settings.model_mode
        if self.manager_factory:
            return self.manager_factory(config)
        if mode == "demo":
            return DemoManager(config)
        return LLMManager(config=config)

    def service(self, run):
        snapshot = dict(run.config_snapshot)
        snapshot.pop("config_hash", None)
        manager = self.manager(AppConfig.model_validate(snapshot), run.model_mode)
        search = DemoSearch if run.model_mode == "demo" else None
        return RunService(manager, search_engine_factory=search)

    def tracing_context(self, mode):
        return tracing_context(enabled=False) if mode == "demo" else nullcontext()

    def check_model_ready(self):
        manager = self.manager()
        try:
            status = manager.get_status()
            if not status["ready"]:
                raise StoreError(
                    503,
                    "model_not_configured",
                    "Missing provider configuration for: " + ", ".join(status["missing_roles"]),
                )
        finally:
            manager.close()

    def asset_path(self, key):
        path = (self.settings.data_dir / "assets" / key).resolve()
        root = (self.settings.data_dir / "assets").resolve()
        if path.parent != root:
            raise StoreError(404, "not_found", "Asset not found")
        return path

    def save_asset(self, owner, data):
        config = self.config()
        if len(data) > min(config.max_image_bytes, self.settings.max_upload_bytes):
            raise StoreError(413, "image_too_large", "Image exceeds upload limit")
        try:
            normalized = validate_image(data, config)
        except ValueError:
            raise StoreError(
                422,
                "invalid_image",
                "Upload a readable JPEG, PNG or WebP within the configured pixel limit",
            ) from None
        if len(normalized) > config.max_image_bytes:
            raise StoreError(
                413,
                "normalized_image_too_large",
                "Normalized image exceeds the limit; resize before upload",
            )
        with Image.open(BytesIO(normalized)) as image:
            width, height = image.size
        identifier = str(uuid4())
        key = f"{identifier}.png"
        path = self.asset_path(key)
        temporary = path.with_suffix(".tmp")
        try:
            with self.db.session() as session:
                session.execute(
                    update(SessionToken)
                    .where(SessionToken.id == owner)
                    .values(last_seen=time.time())
                )
                count = session.scalar(
                    select(func.count()).select_from(Asset).where(Asset.owner_id == owner)
                )
                if count >= self.settings.max_assets_per_owner:
                    raise StoreError(
                        429, "asset_limit", "Asset limit reached; delete unused assets"
                    )
                temporary.write_bytes(normalized)
                os.replace(temporary, path)
                record = Asset(
                    id=identifier,
                    owner_id=owner,
                    storage_key=key,
                    sha256=hashlib.sha256(normalized).hexdigest(),
                    size_bytes=len(normalized),
                    width=width,
                    height=height,
                    created_at=time.time(),
                )
                session.add(record)
            return record
        except BaseException:
            path.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
            raise

    def delete_asset(self, identifier, owner):
        with self.db.session() as session:
            session.execute(
                update(SessionToken).where(SessionToken.id == owner).values(last_seen=time.time())
            )
            asset = owned(session, Asset, identifier, owner)
            if session.scalar(
                select(func.count()).select_from(Run).where(Run.asset_id == asset.id)
            ):
                raise StoreError(409, "asset_in_use", "Asset is referenced by a run")
            session.delete(asset)
            key = asset.storage_key
        self.asset_path(key).unlink(missing_ok=True)
