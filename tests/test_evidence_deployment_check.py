"""Deployment route audits must work from source exports without Git history."""

import shutil
import subprocess

from api.main import create_app
from scripts import evidence_deployment_check as deployment
from tests.test_api import settings as settings


def test_default_baseline_matches_all_mounted_routes_without_git(tmp_path, monkeypatch, settings):
    exported = tmp_path / "exported-source"
    shutil.copytree(
        deployment.ROOT / "api", exported / "api", ignore=shutil.ignore_patterns("__pycache__")
    )
    monkeypatch.setattr(deployment, "ROOT", exported)

    def no_process(*args, **kwargs):
        raise AssertionError("A source-only route audit must not invoke Git")

    monkeypatch.setattr(subprocess, "run", no_process)
    expected = deployment.openapi_operations(create_app(settings).openapi())
    reference, current, baseline = deployment.route_baseline()

    assert not (exported / ".git").exists()
    assert reference == current == expected
    assert baseline == "current source checkout"


def test_explicit_reference_supports_historical_and_split_router_checkouts(tmp_path):
    api = tmp_path / "api"
    api.mkdir()
    (api / "main.py").write_text('@app.get("/legacy")\ndef legacy():\n    pass\n', encoding="utf-8")
    (api / "catalog.py").write_text(
        '@router.get("/heritages")\ndef catalog():\n    pass\n', encoding="utf-8"
    )
    reference, current, baseline = deployment.route_baseline(tmp_path)

    assert reference == {("GET", "/legacy"), ("GET", "/api/v1/heritages")}
    assert current == deployment.checkout_operations(deployment.ROOT)
    assert ("GET", "/legacy") not in current
    assert baseline == "explicit reference checkout"
