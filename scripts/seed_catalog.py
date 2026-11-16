"""Migrate and import the repository catalog without starting workers or models."""

import argparse
import json
import os
from pathlib import Path

# This operator command uses only explicit environment configuration.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api.catalog_schemas import HeritageWrite
from api.catalog_store import CatalogStore
from api.database import Database
from api.settings import ROOT, Settings
from api.store import StoreError


def load_seed(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Expected catalog seed schema_version=1")
    items = document.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Expected a non-empty catalog items array")
    bodies = [HeritageWrite.model_validate(item) for item in items]
    for field, identifiers in (
        ("heritage_id", [body.heritage_id for body in bodies]),
        ("slug", [body.slug for body in bodies]),
        ("media_id", [media.media_id for body in bodies for media in body.media]),
        (
            "source_id",
            [source.source_id for body in bodies for source in body.information_sources],
        ),
    ):
        if any(not identifier for identifier in identifiers):
            raise ValueError(f"Seed requires stable {field} values")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f"Seed contains duplicate {field} values")
    return bodies


def validate_media(bodies, directory):
    root = directory.resolve()
    for body in bodies:
        for media in body.media:
            path = (root / media.storage_key).resolve()
            if path.parent != root or not path.is_file():
                raise ValueError(f"Missing catalog image: {media.storage_key}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "samples/catalog/heritages.json")
    parser.add_argument(
        "--replace", action="store_true", help="Explicitly overwrite records with matching IDs"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate schema/media without connecting to the DB"
    )
    args = parser.parse_args(argv)
    database = None
    try:
        bodies = load_seed(args.input)
        settings = Settings.from_env()
        validate_media(bodies, settings.catalog_media_dir)
        counts = {
            "total": len(bodies),
            "published": sum(body.content_status == "published" for body in bodies),
        }
        if args.dry_run:
            print(json.dumps({"validated": True, **counts}))
            return 0
        database = Database(settings.database_url.get_secret_value())
        config = Config(str(ROOT / "alembic.ini"))
        with database.engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(714802003)"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        result = CatalogStore(database).upsert_seed(
            [body.model_dump(mode="json") for body in bodies], replace=args.replace
        )
        print(json.dumps({**result, **counts}))
        return 0
    except ValidationError:
        parser.exit(1, "Invalid catalog seed fields; no seed records were written.\n")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.exit(1, f"Catalog seed failed: {error}\n")
    except StoreError:
        parser.exit(1, "Catalog identifiers conflict; no seed records were written.\n")
    except SQLAlchemyError:
        parser.exit(1, "Catalog database operation failed; check server configuration.\n")
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
