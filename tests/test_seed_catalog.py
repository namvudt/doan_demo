"""Exercise the operator CLI against isolated SQLite files, without models or workers."""

import json
import os
import sqlite3
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]


def record(identifier="seed-monument-a", **overrides):
    payload = {
        "heritage_id": identifier,
        "slug": identifier,
        "name": "Di tích kiểm thử Hà Nội",
        "province": "Hà Nội",
        "category": "monument",
        "summary": "Hồ sơ kiểm thử lệnh seed, chưa xác minh.",
        "content_status": "published",
        "illustrative": True,
        "location": {
            "latitude": 21.0287,
            "longitude": 105.8522,
            "verification_status": "illustrative",
            "verification_note": "Tọa độ minh họa.",
        },
        "media": [
            {
                "media_id": f"{identifier}-photo",
                "storage_key": "seed-test.png",
                "alt": "Ảnh kiểm thử local",
                "caption": "Ảnh fixture, chưa xác minh.",
                "verified": False,
            }
        ],
        "information_sources": [
            {
                "source_id": f"{identifier}-source",
                "title": "Metadata kiểm thử",
                "url": "https://example.test/reference",
                "verified": False,
                "index_status": "not_indexed",
            }
        ],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def cli(tmp_path, photo):
    media = tmp_path / "media"
    media.mkdir()
    (media / "seed-test.png").write_bytes(photo)
    database = tmp_path / "database" / "catalog.sqlite"
    source = tmp_path / "seed.json"
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("API_") and key != "DATABASE_URL"
    }
    environment.update(
        PYTHON_DOTENV_DISABLED="1",
        PYTHONIOENCODING="utf-8",
        API_ENV="development",
        API_MODEL_MODE="demo",
        API_EMBEDDED_WORKER="false",
        API_DATA_DIR=str(tmp_path / "runtime"),
        API_CATALOG_MEDIA_DIR=str(media),
        DATABASE_URL=f"sqlite:///{database.as_posix()}",
        API_BOOTSTRAP_TOKEN="",
        API_OPERATIONS_TOKEN="",
        LANGSMITH_TRACING="false",
    )

    def run(items, *arguments, env=None):
        source.write_text(
            json.dumps({"schema_version": 1, "items": items}, ensure_ascii=False),
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, "-m", "scripts.seed_catalog", "--input", str(source), *arguments],
            cwd=ROOT,
            env={**environment, **(env or {})},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )

    return run, database, media


def contents(database):
    with sqlite3.connect(database) as connection:
        return list(connection.iterdump())


def test_invalid_later_item_is_rejected_before_database_or_migrations(cli):
    run, database, _ = cli
    result = run([record(), record("seed-invalid", location={"latitude": 91, "longitude": 0})])

    assert result.returncode == 1
    assert "Invalid catalog seed fields" in result.stderr
    assert "Traceback" not in result.stderr
    assert not database.exists()
    assert not database.parent.exists()


@pytest.mark.parametrize("field", ["heritage_id", "slug", "media_id", "source_id"])
def test_duplicate_stable_identifiers_are_rejected_before_database_write(cli, field):
    run, database, _ = cli
    first, second = record(), record("seed-monument-b")
    if field in {"heritage_id", "slug"}:
        second[field] = first[field]
    elif field == "media_id":
        second["media"][0][field] = first["media"][0][field]
    else:
        second["information_sources"][0][field] = first["information_sources"][0][field]
    result = run([first, second])

    assert result.returncode == 1
    assert f"duplicate {field}" in result.stderr
    assert not database.exists()


def test_missing_media_preserves_existing_database_without_partial_import(cli):
    run, database, _ = cli
    assert run([record()]).returncode == 0
    before = contents(database)
    new_record = record("seed-monument-b")
    missing_record = record("seed-missing-photo")
    missing_record["media"][0]["storage_key"] = "missing.png"

    result = run([new_record, missing_record])

    assert result.returncode == 1
    assert "Missing catalog image: missing.png" in result.stderr
    assert contents(database) == before


def test_dry_run_validates_media_without_connecting_to_a_database(cli):
    run, database, _ = cli
    result = run(
        [record()],
        "--dry-run",
        env={"DATABASE_URL": "not-a-real-database-driver://unreachable"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"validated": True, "total": 1, "published": 1}
    assert not database.exists()
    assert not database.parent.exists()


def test_actual_cli_migrates_idempotently_preserves_edits_and_replaces_only_explicitly(cli):
    run, database, _ = cli
    original = record()
    draft = record("seed-private-draft", content_status="draft")
    first = run([original, draft])
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout) == {
        "created": 2,
        "updated": 0,
        "skipped": 0,
        "total": 2,
        "published": 1,
    }
    before = contents(database)
    repeated = run([original, draft])
    assert repeated.returncode == 0, repeated.stderr
    assert json.loads(repeated.stdout)["skipped"] == 2
    assert contents(database) == before

    updated = deepcopy(original)
    updated["name"] = "Tên hồ sơ đã được biên tập"
    updated["media"][0]["caption"] = "Chú thích mới"
    preserved = run([updated, draft])
    assert preserved.returncode == 0, preserved.stderr
    assert contents(database) == before

    replaced = run([updated], "--replace")
    assert replaced.returncode == 0, replaced.stderr
    assert json.loads(replaced.stdout)["updated"] == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head(),
        )
        assert connection.execute(
            "SELECT name, version FROM heritage_sites WHERE id = ?", (original["heritage_id"],)
        ).fetchone() == (updated["name"], 2)
        for table in (
            "heritage_sites",
            "heritage_site_information",
            "heritage_site_media",
            "heritage_content_sources",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (2,)
        assert connection.execute(
            "SELECT caption FROM heritage_site_media WHERE id = ?",
            (original["media"][0]["media_id"],),
        ).fetchone() == ("Chú thích mới",)
        assert connection.execute(
            "SELECT DISTINCT index_status FROM heritage_content_sources"
        ).fetchall() == [("not_indexed",)]
        for table in ("api_sessions", "api_assets", "api_runs", "api_workers"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
