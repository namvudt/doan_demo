"""Offline-model HTTP smoke with official local Prometheus/promtool binaries.

Example: python -m scripts.monitoring_smoke --prometheus path/to/prometheus.exe
--promtool path/to/promtool.exe. Owns and stops only the processes it creates.
"""

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise AssertionError(message)


def wait_for(check, children, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        require(all(child.poll() is None for child in children), "Managed process exited early")
        try:
            value = check()
            if value:
                return value
        except (httpx.HTTPError, KeyError, IndexError):
            pass
        time.sleep(0.2)
    raise AssertionError("Managed monitoring verification timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prometheus", required=True, type=Path)
    parser.add_argument("--promtool", required=True, type=Path)
    parser.add_argument("--api-port", type=int, default=18513)
    parser.add_argument("--prometheus-port", type=int, default=19091)
    args = parser.parse_args()
    for binary in (args.prometheus, args.promtool):
        require(binary.is_file(), "Provide a local official Prometheus/promtool executable")
    require(args.api_port != args.prometheus_port, "Managed services need distinct ports")
    for port in (args.api_port, args.prometheus_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    work = ROOT / ".api-demo" / ("monitoring-" + uuid4().hex)
    work.mkdir(parents=True)
    token = secrets.token_urlsafe(40)
    credential_file = work / "operations_token"
    credential_file.write_text(token, encoding="utf-8")
    config = yaml.safe_load((ROOT / "monitoring/prometheus.yml").read_text(encoding="utf-8"))
    config["global"] = {"scrape_interval": "1s", "evaluation_interval": "1s"}
    config["rule_files"] = [(ROOT / "monitoring/alerts.yml").as_posix()]
    job = config["scrape_configs"][0]
    job["authorization"]["credentials_file"] = credential_file.as_posix()
    job["static_configs"][0]["targets"] = [f"127.0.0.1:{args.api_port}"]
    config_file = work / "prometheus.yml"
    config_file.write_text(yaml.safe_dump(config), encoding="utf-8")
    env = {
        **os.environ,
        "PYTHON_DOTENV_DISABLED": "1",
        "LANGSMITH_TRACING": "false",
        "API_ENV": "development",
        "API_MODEL_MODE": "demo",
        "API_EMBEDDED_WORKER": "true",
        "API_BOOTSTRAP_TOKEN": "",
        "API_OPERATIONS_TOKEN": token,
        "API_DATA_DIR": str(work / "assets"),
        "API_LOG_DIR": str(work / "logs"),
        "API_LOG_LEVEL": "INFO",
        "DATABASE_URL": "sqlite:///" + (work / "api.sqlite").as_posix(),
    }
    children, report = [], {"model_mode": "demo", "paid_model_calls": 0, "checks": {}}

    def launch(arguments):
        child = subprocess.Popen(
            arguments, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        children.append(child)
        return child

    try:
        checked = subprocess.run(
            [str(args.promtool.resolve()), "check", "config", str(config_file)],
            cwd=ROOT,
            capture_output=True,
            timeout=20,
        )
        require(checked.returncode == 0, "Promtool config validation failed")
        report["checks"]["promtool_config"] = "passed"
        launch([sys.executable, "-m", "scripts.serve_api", "--demo", "--port", str(args.api_port)])
        with httpx.Client(base_url=f"http://127.0.0.1:{args.api_port}", timeout=5) as api:
            wait_for(lambda: api.get("/health/ready").status_code == 200, children)
            launch(
                [
                    str(args.prometheus.resolve()),
                    "--config.file=" + str(config_file),
                    "--storage.tsdb.path=" + str(work / "tsdb"),
                    f"--web.listen-address=127.0.0.1:{args.prometheus_port}",
                ]
            )
            with httpx.Client(
                base_url=f"http://127.0.0.1:{args.prometheus_port}", timeout=5
            ) as prom:
                wait_for(lambda: prom.get("/-/ready").status_code == 200, children)

                def query(expression):
                    response = prom.get("/api/v1/query", params={"query": expression})
                    response.raise_for_status()
                    values = response.json()["data"]["result"]
                    return float(values[0]["value"][1]) if values else None

                wait_for(lambda: query('up{job="heritage-api"}') == 1, children)
                report["checks"]["authenticated_scrape"] = "passed"
                response = api.post("/api/v1/sessions", json={})
                require(response.status_code == 201, "Session creation failed")
                auth = {"Authorization": "Bearer " + response.json()["access_token"]}
                buffer = BytesIO()
                Image.new("RGB", (40, 30), "green").save(buffer, format="PNG")
                asset = api.post(
                    "/api/v1/assets",
                    headers=auth,
                    files={"file": ("demo.png", buffer.getvalue(), "image/png")},
                )
                require(asset.status_code == 201, "Asset upload failed")
                response = api.post(
                    "/api/v1/runs",
                    headers=auth,
                    json={
                        "asset_id": asset.json()["asset_id"],
                        "question": "PRIVATE_SMOKE_QUESTION",
                    },
                )
                require(response.status_code == 202, "Run creation failed")
                identifier = response.json()["run_id"]
                wait_for(
                    lambda: (
                        api.get(f"/api/v1/runs/{identifier}", headers=auth).json()[
                            "execution_status"
                        ]
                        == "succeeded"
                    ),
                    children,
                )
                for label, expression, expected in (
                    ("worker_alive", "heritage_workers_alive", 1),
                    ("durable_run", 'heritage_runs{status="succeeded"}', 1),
                    ("durable_attempts", 'heritage_model_attempts{status="success"}', 5),
                    ("unknown_usage", "heritage_model_attempts_unknown_usage", 5),
                    (
                        "http_counter",
                        'sum(heritage_http_requests_total{route="/api/v1/runs",status="202"})',
                        1,
                    ),
                ):
                    wait_for(lambda: query(expression) == expected, children)
                    report["checks"][label] = "passed"
                rules = prom.get("/api/v1/rules").json()["data"]["groups"][0]["rules"]
                require(
                    len(rules) == 6 and all(r["health"] == "ok" for r in rules),
                    "Alert evaluation failed",
                )
                report["checks"]["six_alert_rules_evaluated"] = "passed"
                exposition = api.get(
                    "/api/v1/operations/metrics", headers={"Authorization": "Bearer " + token}
                ).text
                checked = subprocess.run(
                    [str(args.promtool.resolve()), "check", "metrics"],
                    input=exposition.encode(),
                    capture_output=True,
                    timeout=20,
                )
                require(checked.returncode == 0, "Prometheus exposition validation failed")
                report["checks"]["promtool_exposition"] = "passed"
                raw_logs = "\n".join(
                    path.read_text(encoding="utf-8") for path in (work / "logs").glob("*.jsonl")
                )
                require(
                    token not in raw_logs and "PRIVATE_SMOKE_QUESTION" not in raw_logs,
                    "Private data appeared in logs",
                )
                report["checks"]["log_privacy"] = "passed"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        if isinstance(exc, AssertionError):
            report["error"] = str(exc)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
        credential_file.unlink(missing_ok=True)
    target = ROOT / "reports/monitoring/results.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return int("error_type" in report)


if __name__ == "__main__":
    raise SystemExit(main())
