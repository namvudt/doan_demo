"""Restore-rehearse a local demo backup in an owned temporary database/container."""

import argparse
import json
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "heritage-fe-local"
DB_CONTAINER = "heritage-fe-local-db-1"
NETWORK = "heritage-fe-local_default"
DB_USER = "heritage_demo"
LABEL = "io.heritage.restore.id"


class RehearsalError(Exception):
    """Safe public error containing a stage name, never subprocess output."""


def safe_backup_directory(value, root=ROOT):
    path = Path(value).resolve()
    anchor = (root / ".api-demo" / "backups").resolve()
    if not path.is_relative_to(anchor) or not path.is_dir() or "," in str(path):
        raise RehearsalError("Backup must be an existing directory inside .api-demo/backups")
    for name in ("demo-postgres.dump", "demo-assets.tar.gz", "record-fingerprints.json"):
        candidate = (path / name).resolve()
        if not candidate.is_relative_to(path) or not candidate.is_file():
            raise RehearsalError("Backup is missing a required local-demo artifact")
    return path


def safe_archive_member(member):
    name = member.name
    posix = PurePosixPath(name)
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or posix.is_absolute()
        or PureWindowsPath(name).drive
        or ".." in posix.parts
        or not (member.isfile() or member.isdir())
    ):
        raise RehearsalError("Asset archive contains an unsafe path or member type")
    return posix.as_posix()


def validate_archive(path):
    count, total, names = 0, 0, set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = safe_archive_member(member)
            if member.isfile():
                if name in names:
                    raise RehearsalError("Asset archive contains duplicate files")
                names.add(name)
                total += member.size
            count += 1
            if count > 100000 or total > 2_000_000_000:
                raise RehearsalError("Asset archive exceeds rehearsal resource limits")
    return {"members": count, "bytes": total}


def temporary_names(nonce):
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise RehearsalError("Invalid rehearsal ownership identifier")
    return "heritage_restore_" + nonce, "heritage-restore-check-" + nonce


def validate_owned_name(name, nonce, *, container=False):
    database, qa_container = temporary_names(nonce)
    if name != (qa_container if container else database):
        raise RehearsalError("Refusing cleanup of a resource not created by this rehearsal")


def validate_demo_container(info):
    labels = info.get("Config", {}).get("Labels") or {}
    if (
        info.get("Name") != "/" + DB_CONTAINER
        or labels.get("com.docker.compose.project") != PROJECT
        or labels.get("com.docker.compose.service") != "db"
        or not info.get("State", {}).get("Running")
    ):
        raise RehearsalError("Refusing a database outside the running heritage local-demo project")
    if NETWORK not in info.get("NetworkSettings", {}).get("Networks", {}):
        raise RehearsalError("Demo database is not attached to the expected local network")


def docker(arguments, stage, *, stdin=None, allow_failure=False, timeout=180):
    try:
        result = subprocess.run(
            ["docker", *arguments], stdin=stdin, capture_output=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RehearsalError(f"Docker stage failed: {stage}") from None
    if result.returncode and not allow_failure:
        raise RehearsalError(f"Docker stage failed: {stage}")
    return result


RUNTIME_PROGRAM = r"""
import hashlib, json, os, shutil, sys, tarfile, tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
os.environ['PYTHON_DOTENV_DISABLED']='1'
from sqlalchemy import select, text
from PIL import Image
from api.models import Asset, HeritageSite, HeritageSiteMedia
from api.runtime import Runtime
from api.settings import Settings

def require(condition, code):
    if not condition: raise RuntimeError(code)

runtime=None
try:
    source=Path('/restore-input')
    baseline=json.loads((source/'record-fingerprints.json').read_text(encoding='utf-8-sig'))
    target=Path(tempfile.mkdtemp(prefix='heritage-restore-'))/'data'
    target.mkdir()
    seen=set()
    with tarfile.open(source/'demo-assets.tar.gz','r:gz') as archive:
        for member in archive:
            name=member.name
            relative=PurePosixPath(name)
            require(name and chr(92) not in name and chr(0) not in name and not relative.is_absolute()
                    and not PureWindowsPath(name).drive and '..' not in relative.parts
                    and (member.isfile() or member.isdir()),'unsafe_archive_member')
            destination=(target/relative).resolve()
            require(destination.is_relative_to(target.resolve()),'archive_path_escape')
            if member.isdir():
                destination.mkdir(parents=True,exist_ok=True)
            else:
                require(relative.as_posix() not in seen,'duplicate_archive_file')
                seen.add(relative.as_posix())
                destination.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(member) as reader, destination.open('xb') as writer:
                    shutil.copyfileobj(reader,writer)
    os.environ['API_DATA_DIR']=str(target)
    os.environ['API_LOG_DIR']=str(target.parent/'logs')
    settings=Settings.from_env()
    require(settings.model_mode=='demo','demo_required')
    runtime=Runtime(settings)
    runtime.migrate()
    queries={
      'runs': "SELECT id,md5(coalesce(result::text,'')) FROM api_runs",
      'assets': 'SELECT id,sha256,storage_key FROM api_assets',
      'catalog': 'SELECT id,version,updated_at FROM heritage_sites',
    }
    preserved={}
    with runtime.db.session() as session:
        for kind,query in queries.items():
            expected={row[0]:row for row in baseline[kind]}
            actual={row[0]:list(row) for row in session.execute(text(query)).all()}
            require(actual==expected,'baseline_'+kind+'_changed')
            preserved[kind]=len(expected)
        revision=session.scalar(text('SELECT version_num FROM alembic_version'))
        require(revision=='0009_runtime_state','unexpected_migration_head')
        assets=list(session.scalars(select(Asset)))
        for asset in assets:
            path=runtime.asset_path(asset.storage_key)
            require(path.is_file(),'referenced_asset_missing')
            data=path.read_bytes()
            require(len(data)==asset.size_bytes and hashlib.sha256(data).hexdigest()==asset.sha256,'asset_hash_mismatch')
            with Image.open(path) as image:
                image.load()
                require(image.size==(asset.width,asset.height),'asset_dimensions_mismatch')
        media=list(session.execute(select(HeritageSiteMedia,HeritageSite.id)
             .join(HeritageSite,HeritageSite.id==HeritageSiteMedia.heritage_id)
             .where(HeritageSite.content_status=='published')).all())
        require(len(media)==int(os.environ.get('RESTORE_EXPECTED_CATALOG_IMAGES','7')),'published_catalog_image_count_mismatch')
        from api.catalog_store import CatalogStore
        for photo,heritage_id in media:
            path=CatalogStore(runtime.db).media_path(heritage_id,photo.id,settings.catalog_media_dir,settings.data_dir/'catalog-media')
            with Image.open(path) as image:
                image.load()
                require(min(image.size)>0,'catalog_image_decode_failed')
    print(json.dumps({'passed':True,'migration_head':revision,'preserved':preserved,
                      'assets_hash_checked':len(assets),'assets_decoded':len(assets),
                      'catalog_images_decoded':len(media),
                      'backend_build':os.environ.get('HERITAGE_BUILD_REVISION','development')}))
except Exception:
    print(json.dumps({'passed':False,'error':'Restored database, migration or asset validation failed'}))
    sys.exit(1)
finally:
    if runtime is not None: runtime.db.close()
"""


def rehearse(backup, image, report, *, catalog_images=7):
    inspected = json.loads(docker(["inspect", DB_CONTAINER], "inspect project").stdout)[0]
    validate_demo_container(inspected)
    network = json.loads(docker(["network", "inspect", NETWORK], "inspect network").stdout)[0]
    if (network.get("Labels") or {}).get("com.docker.compose.project") != PROJECT:
        raise RehearsalError("Refusing a network outside the local-demo project")
    if not (
        image.startswith("heritage-frontend-backend:")
        or re.fullmatch(r"sha256:[a-f0-9]{64}", image)
    ):
        raise RehearsalError("Use a locally built heritage backend image")
    docker(["image", "inspect", image], "inspect local image")
    with (backup / "demo-postgres.dump").open("rb") as artifact:
        if artifact.read(5) != b"PGDMP":
            raise RehearsalError("Expected a custom-format PostgreSQL backup")
    report["archive"] = validate_archive(backup / "demo-assets.tar.gz")
    baseline = json.loads((backup / "record-fingerprints.json").read_text(encoding="utf-8-sig"))
    if not all(isinstance(baseline.get(key), list) for key in ("runs", "assets", "catalog")):
        raise RehearsalError("Invalid baseline fingerprint metadata")
    nonce = uuid4().hex
    temporary_database, temporary_container = temporary_names(nonce)
    created = False
    report["cleanup"] = {"temporary_database_removed": False, "temporary_container_removed": False}
    try:
        existing = docker(
            [
                "exec",
                DB_CONTAINER,
                "psql",
                "-U",
                DB_USER,
                "-d",
                DB_USER,
                "-Atc",
                f"SELECT 1 FROM pg_database WHERE datname='{temporary_database}'",
            ],
            "verify unused database name",
        )
        if existing.stdout.strip():
            raise RehearsalError("Generated database name is already in use")
        docker(
            [
                "exec",
                DB_CONTAINER,
                "createdb",
                "-U",
                DB_USER,
                "--owner",
                DB_USER,
                "--template",
                "template0",
                temporary_database,
            ],
            "create owned temporary database",
        )
        created = True
        with (backup / "demo-postgres.dump").open("rb") as dump:
            docker(
                [
                    "exec",
                    "-i",
                    DB_CONTAINER,
                    "pg_restore",
                    "-U",
                    DB_USER,
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                    "--dbname",
                    temporary_database,
                ],
                "restore custom dump",
                stdin=dump,
            )
        # Only the generated database is reachable through the explicitly supplied URL.
        url = f"postgresql+psycopg://heritage_demo:local-demo-only@{DB_CONTAINER}:5432/{temporary_database}"
        args = [
            "run",
            "--rm",
            "--name",
            temporary_container,
            "--label",
            f"{LABEL}={nonce}",
            "--network",
            NETWORK,
            "--mount",
            f"type=bind,source={backup},target=/restore-input,readonly",
        ]
        environment = {
            "DATABASE_URL": url,
            "API_ENV": "development",
            "API_MODEL_MODE": "demo",
            "API_EMBEDDED_WORKER": "false",
            "PYTHON_DOTENV_DISABLED": "1",
            "LANGSMITH_TRACING": "false",
            "LANGSMITH_CAPTURE_CONTENT": "false",
            "API_BOOTSTRAP_TOKEN": "",
            "API_OPERATIONS_TOKEN": "",
            "GEMINI_API_KEY": "",
            "OPENAI_API_KEY": "",
            "KNOWLEDGE_API_KEY": "",
            "JUDGE_API_KEY": "",
            "LANGSMITH_API_KEY": "",
            "RESTORE_EXPECTED_CATALOG_IMAGES": str(catalog_images),
        }
        for key, value in environment.items():
            args.extend(["-e", f"{key}={value}"])
        result = docker(
            [*args, image, "python", "-c", RUNTIME_PROGRAM], "migrate and verify restored data"
        )
        lines = result.stdout.decode("utf-8").strip().splitlines()
        validation = json.loads(lines[-1]) if lines else {}
        if not validation.get("passed"):
            raise RehearsalError("Restored data validation did not succeed")
        report.update(validation)
    finally:
        validate_owned_name(temporary_container, nonce, container=True)
        remaining = docker(
            ["inspect", temporary_container], "inspect owned cleanup container", allow_failure=True
        )
        if not remaining.returncode:
            info = json.loads(remaining.stdout)[0]
            if (
                info.get("Name") != "/" + temporary_container
                or (info.get("Config", {}).get("Labels") or {}).get(LABEL) != nonce
            ):
                raise RehearsalError(
                    "Refusing removal of a container without this rehearsal ownership label"
                )
            docker(["rm", "-f", temporary_container], "remove owned temporary container")
        report["cleanup"]["temporary_container_removed"] = True
        if created:
            validate_owned_name(temporary_database, nonce)
            owner = docker(
                [
                    "exec",
                    DB_CONTAINER,
                    "psql",
                    "-U",
                    DB_USER,
                    "-d",
                    DB_USER,
                    "-Atc",
                    f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='{temporary_database}'",
                ],
                "verify temporary database ownership",
            )
            if owner.stdout.strip() not in {b"", DB_USER.encode()}:
                raise RehearsalError("Refusing cleanup of a database with different ownership")
            docker(
                [
                    "exec",
                    DB_CONTAINER,
                    "dropdb",
                    "-U",
                    DB_USER,
                    "--if-exists",
                    "--force",
                    temporary_database,
                ],
                "drop owned temporary database",
            )
            report["cleanup"]["temporary_database_removed"] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--image", default="heritage-frontend-backend:demo")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--catalog-images", type=int, default=7)
    args = parser.parse_args(argv)
    if not 0 <= args.catalog_images <= 100000:
        parser.error("Catalog image count must be between 0 and 100000")
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": False,
        "project": PROJECT,
        "paid_model_calls": False,
    }
    output = None
    try:
        backup = safe_backup_directory(args.backup)
        candidate_output = (args.output or backup / "restore-verification.json").resolve()
        if (
            not candidate_output.is_relative_to((ROOT / ".api-demo").resolve())
            or candidate_output.suffix != ".json"
            or candidate_output.name in {"record-fingerprints.json", "manifest-sha256.json"}
        ):
            raise RehearsalError("Report must be a separate JSON artifact inside .api-demo")
        output = candidate_output
        rehearse(backup, args.image, report, catalog_images=args.catalog_images)
        report["passed"] = True
    except RehearsalError as error:
        report["passed"] = False
        report["error"] = str(error)
    except (OSError, tarfile.TarError, ValueError, KeyError, IndexError, TypeError):
        report["passed"] = False
        report["error"] = (
            "Local demo restore rehearsal failed; no command output or credentials are recorded"
        )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
