"""Safety guards for a rehearsal; these tests never invoke Docker."""

import io
import subprocess
import tarfile
from types import SimpleNamespace

import pytest

from scripts import verify_backup
from scripts.verify_backup import (
    DB_CONTAINER,
    NETWORK,
    PROJECT,
    RUNTIME_PROGRAM,
    RehearsalError,
    docker,
    safe_backup_directory,
    temporary_names,
    validate_archive,
    validate_demo_container,
    validate_owned_name,
)


def archive(path, name="./assets/image.png", kind=tarfile.REGTYPE):
    with tarfile.open(path, "w:gz") as handle:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.size = 4 if kind == tarfile.REGTYPE else 0
        member.linkname = "outside"
        handle.addfile(member, io.BytesIO(b"data") if member.size else None)


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../outside", tarfile.REGTYPE),
        ("/absolute", tarfile.REGTYPE),
        ("C:\\outside", tarfile.REGTYPE),
        ("assets/link", tarfile.SYMTYPE),
        ("assets/hardlink", tarfile.LNKTYPE),
        ("assets/device", tarfile.CHRTYPE),
    ],
)
def test_archive_escape_and_special_members_are_rejected_before_extraction(tmp_path, name, kind):
    path = tmp_path / "assets.tar.gz"
    archive(path, name, kind)
    with pytest.raises(RehearsalError):
        validate_archive(path)
    assert not (tmp_path / "outside").exists()


def test_relative_regular_archive_and_frozen_runtime_program_are_valid(tmp_path):
    path = tmp_path / "assets.tar.gz"
    archive(path)
    assert validate_archive(path) == {"members": 1, "bytes": 4}
    compile(RUNTIME_PROGRAM, "restore-rehearsal-runtime", "exec")


def test_backup_guard_requires_project_backup_location_and_all_artifacts(tmp_path):
    folder = tmp_path / ".api-demo" / "backups" / "case"
    folder.mkdir(parents=True)
    with pytest.raises(RehearsalError):
        safe_backup_directory(folder, root=tmp_path)
    for name in ("demo-postgres.dump", "demo-assets.tar.gz", "record-fingerprints.json"):
        (folder / name).write_bytes(b"fixture")
    assert safe_backup_directory(folder, root=tmp_path) == folder.resolve()
    with pytest.raises(RehearsalError):
        safe_backup_directory(tmp_path, root=tmp_path)


def test_cleanup_targets_require_this_exact_nonce_and_resource_name():
    nonce = "a" * 32
    database, container = temporary_names(nonce)
    validate_owned_name(database, nonce)
    validate_owned_name(container, nonce, container=True)
    for name in ("heritage_demo", "postgres", "heritage_restore_" + "b" * 32):
        with pytest.raises(RehearsalError):
            validate_owned_name(name, nonce)
    with pytest.raises(RehearsalError):
        temporary_names("../../arbitrary")


def test_only_running_demo_compose_database_can_be_targeted():
    info = {
        "Name": "/" + DB_CONTAINER,
        "Config": {
            "Labels": {"com.docker.compose.project": PROJECT, "com.docker.compose.service": "db"}
        },
        "State": {"Running": True},
        "NetworkSettings": {"Networks": {NETWORK: {}}},
    }
    validate_demo_container(info)
    info["Config"]["Labels"]["com.docker.compose.project"] = "unrelated-project"
    with pytest.raises(RehearsalError):
        validate_demo_container(info)


def test_docker_errors_do_not_expose_command_output_or_connection_credentials(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout=b"connection password private", stderr=b"bearer private"
        ),
    )
    with pytest.raises(RehearsalError) as error:
        docker(["inspect", "fixture"], "safe stage")
    assert str(error.value) == "Docker stage failed: safe stage"
    assert "private" not in str(error.value)


def test_invalid_output_cannot_overwrite_a_server_env_or_fingerprint_file(tmp_path, monkeypatch):
    backup = tmp_path / ".api-demo" / "backups" / "fixture"
    backup.mkdir(parents=True)
    private = tmp_path / ".env"
    private.write_text("private fixture that must not change")
    fingerprints = backup / "record-fingerprints.json"
    fingerprints.write_text("preserve baseline")
    monkeypatch.setattr(verify_backup, "ROOT", tmp_path)
    monkeypatch.setattr(verify_backup, "safe_backup_directory", lambda value: backup)

    def no_docker(*args, **kwargs):
        raise AssertionError("Invalid report paths must be rejected before Docker")

    monkeypatch.setattr(verify_backup, "rehearse", no_docker)
    assert verify_backup.main(["fixture", "--output", str(private)]) == 1
    assert verify_backup.main(["fixture", "--output", str(fingerprints)]) == 1
    assert private.read_text() == "private fixture that must not change"
    assert fingerprints.read_text() == "preserve baseline"
