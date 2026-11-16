"""Acceptance checks for merging independently deployed catalog/evidence histories."""

import json

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text

from api.catalog_store import CatalogStore
from api.database import Database
from api.main import create_app
from api.models import Run
from api.settings import ROOT
from tests.test_api import settings as settings

HEAD = "0009_runtime_state"


def test_catalog_and_evidence_have_one_migration_head():
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert scripts.get_heads() == [HEAD]
    assert set(scripts.get_revision("0006_merge_evidence_catalog").down_revision) == {
        "0005_heritage_catalog",
        "0005_input_context",
    }


@pytest.mark.parametrize("starting_revision", ["0005_heritage_catalog", "0005_input_context"])
def test_merge_upgrade_preserves_each_previously_deployed_history(settings, starting_revision):
    database = Database(settings.database_url.get_secret_value())
    config = Config(str(ROOT / "alembic.ini"))
    try:
        with database.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, starting_revision)
            connection.execute(
                text(
                    "INSERT INTO api_sessions "
                    "(id,token_hash,label,created_at,expires_at,last_seen,revoked) "
                    "VALUES ('legacy','legacy-hash','keep session',0,1000,0,false)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO api_assets "
                    "(id,owner_id,storage_key,sha256,size_bytes,width,height,created_at) "
                    "VALUES ('legacy-photo','legacy','legacy.png','hash',1,1,1,0)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO api_runs "
                    "(id,owner_id,asset_id,question,audience,profile,model_mode,execution_status,"
                    "config_snapshot,request_hash,cancel_requested,bookmarked,event_count,created_at) "
                    "VALUES ('legacy-run','legacy','legacy-photo','keep question','tourist',"
                    "'default','demo','succeeded','{}','hash',false,false,1,0)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO api_run_events (run_id,sequence,event,payload,created_at) "
                    "VALUES ('legacy-run',1,'run.succeeded','{}',0)"
                )
            )
            if starting_revision == "0005_input_context":
                connection.execute(
                    text(
                        'UPDATE api_runs SET input_context = \'{"answer":"keep context"}\', '
                        "run_kind='clarification' WHERE id='legacy-run'"
                    )
                )
        catalog_seed = {
            "heritage_id": "keep-site",
            "name": "Preserved catalog",
            "slug": "keep-site",
            "category": "monument",
            "content_status": "published",
            "illustrative": True,
        }
        catalog_before = None
        if starting_revision == "0005_heritage_catalog":
            CatalogStore(database).upsert_seed([catalog_seed])
            catalog_before = CatalogStore(database).get_public("keep-site")
        with database.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
            )
            assert (
                connection.execute(text("SELECT label FROM api_sessions")).scalar()
                == "keep session"
            )
            assert connection.execute(text("SELECT count(*) FROM api_run_events")).scalar() == 1
            command.check(config)
        with database.session() as session:
            run = session.scalar(select(Run).where(Run.id == "legacy-run"))
            assert run.question == "keep question"
            assert run.asset_id == "legacy-photo"
            assert run.input_context == (
                {"answer": "keep context"} if starting_revision == "0005_input_context" else None
            )
            assert run.run_kind == (
                "clarification" if starting_revision == "0005_input_context" else "full"
            )
        if catalog_before:
            assert CatalogStore(database).get_public("keep-site") == catalog_before
        else:
            assert CatalogStore(database).upsert_seed([catalog_seed])["created"] == 1
        assert "heritage_sites" in inspect(database.engine).get_table_names()
    finally:
        database.close()


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("evidence-7e4bc8988853-catalog-test", "evidence-7e4bc8988853-catalog-test"),
        ("bad\r\nvalue", "unknown"),
    ],
)
def test_build_identity_and_combined_capabilities(settings, monkeypatch, configured, expected):
    monkeypatch.setenv("HERITAGE_BUILD_REVISION", configured)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/capabilities", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 200
        assert response.headers["X-Backend-Build"] == expected
        assert "X-Backend-Build" in response.headers["access-control-expose-headers"]
        capabilities = response.json()
        assert capabilities["accuracy"]["enabled"] is False
        assert capabilities["features"]["heritage_catalog"] is True
        assert capabilities["features"]["heritage_asset_import"] is True
        assert client.get("/api/v1/runs").headers["X-Backend-Build"] == expected
        schema = client.get("/openapi.json").json()
        assert schema["info"]["version"] == "1.2.0"
        assert "/api/v1/runs/{run_id}/evidence" in schema["paths"]
        assert "/api/v1/runs/{run_id}/clarification" in schema["paths"]
        assert "/api/v1/runs/{run_id}/regions/{region_id}/image" in schema["paths"]
        assert "/api/v1/heritages" in schema["paths"]
        assert "GEMINI_API_KEY" not in json.dumps(capabilities)
