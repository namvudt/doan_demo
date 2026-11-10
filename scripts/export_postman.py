"""Export complete Postman v2.1 artifacts from the application's OpenAPI contract."""

import argparse
import json
from copy import deepcopy
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"

DEFAULTS = {
    "base_url": "http://127.0.0.1:8001",
    "bootstrap_token": "",
    "operations_token": "",
    "access_token": "",
    "session_id": "",
    "session_label": "Postman Heritage VQA",
    "sample_id": "chua_mot_cot",
    "asset_id": "",
    "run_id": "",
    "retry_run_id": "",
    "delete_asset_id": "",
    "question": "Những chi tiết kiến trúc nào nhìn thấy rõ trong ảnh?",
    "audience": "tourist",
    "profile": "default",
    "idempotency_key": "",
    "retry_idempotency_key": "",
    "history_after": "0",
    "sse_after": "0",
    "last_event_id": "0",
    "include_draft": "false",
    "include_intermediate": "false",
    "poll_interval_ms": "1000",
    "poll_max_attempts": "120",
    "feedback_note": "Nguồn và tiến trình dễ quan sát.",
    "feedback_rating": "helpful",
    "bookmark_saved": "true",
    "enable_upload": "false",
    "run_lifecycle_actions": "false",
}
SECRET_KEYS = {"access_token", "bootstrap_token", "operations_token"}

# Ordering also provides a ready-to-run workflow, with optional actions last.
REQUESTS = [
    ("01 System", "GET", "/health/live", "Liveness"),
    ("01 System", "GET", "/health/ready", "Readiness"),
    ("01 System", "GET", "/api/v1/capabilities", "Capabilities and model mode"),
    ("01 System", "GET", "/api/v1/samples", "List sample images"),
    ("02 Session", "POST", "/api/v1/sessions", "Create session and save access token"),
    ("02 Session", "GET", "/api/v1/sessions/me", "Current session"),
    ("03 Assets", "POST", "/api/v1/samples/{sample_id}/assets", "Create asset from sample"),
    ("03 Assets", "GET", "/api/v1/assets", "List assets"),
    ("03 Assets", "GET", "/api/v1/assets/{asset_id}", "Asset metadata"),
    ("03 Assets", "GET", "/api/v1/assets/{asset_id}/content", "Download normalized PNG"),
    ("03 Assets", "POST", "/api/v1/assets", "Upload image - optional"),
    ("04 Workflow", "GET", "/api/v1/workflow", "Workflow stages and diagram"),
    ("05 Runs", "POST", "/api/v1/runs", "Create run and save run ID"),
    ("05 Runs", "GET", "/api/v1/runs", "List runs"),
    ("05 Runs", "GET", "/api/v1/runs/{run_id}", "Wait for run - Runner polling"),
    ("06 Events", "GET", "/api/v1/runs/{run_id}/events/history", "Event history JSON"),
    ("06 Events", "GET", "/api/v1/runs/{run_id}/events", "Stream stages SSE"),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/result", "Final result"),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/sources", "Sources and citations"),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/steps", "Intermediate stage snapshots"),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/metrics", "Durable model attempts and usage"),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/export", "Export JSON"),
    ("08 Feedback", "PUT", "/api/v1/runs/{run_id}/bookmark", "Save bookmark"),
    ("08 Feedback", "POST", "/api/v1/runs/{run_id}/feedback", "Create feedback"),
    ("08 Feedback", "PUT", "/api/v1/runs/{run_id}/feedback", "Update feedback"),
    ("08 Feedback", "GET", "/api/v1/runs/{run_id}/feedback", "Read feedback"),
    ("09 Operations", "GET", "/api/v1/operations/metrics", "Prometheus metrics - operator token"),
    ("10 Lifecycle actions - optional", "POST", "/api/v1/runs/{run_id}/cancel", "Cancel run"),
    (
        "10 Lifecycle actions - optional",
        "POST",
        "/api/v1/runs/{run_id}/retry",
        "Retry terminal run - saves retry_run_id",
    ),
    (
        "10 Lifecycle actions - optional",
        "DELETE",
        "/api/v1/assets/{asset_id}",
        "Delete asset - 409 if used",
    ),
    (
        "10 Lifecycle actions - optional",
        "DELETE",
        "/api/v1/sessions/me",
        "Revoke session - run last",
    ),
]


def script(kind, source):
    return {
        "listen": kind,
        "script": {"type": "text/javascript", "exec": source.strip().splitlines()},
    }


def uid(value):
    return str(uuid5(NAMESPACE_URL, "heritage-vqa/postman/" + value))


def root_scripts():
    return [
        script(
            "prerequest",
            r"""
const base = String(pm.variables.get('base_url') || '').replace(/\/+$/, '');
if (!/^https?:\/\//.test(base)) throw new Error('Set base_url and select the imported environment.');
pm.variables.set('base_url', base);
['question', 'feedback_note', 'session_label'].forEach(key => {
  pm.variables.set(key + '_json', JSON.stringify(String(pm.variables.get(key) || '')));
});
""",
        ),
        script(
            "test",
            """
pm.test('Response has a request ID', () => {
  pm.expect(pm.response.headers.get('X-Request-ID')).to.match(/^[a-f0-9-]{36}$/i);
});
""",
        ),
    ]


def query_parameters(operation):
    entries = []
    for parameter in operation.get("parameters", []):
        if parameter["in"] != "query":
            continue
        name, schema = parameter["name"], parameter.get("schema", {})
        value = schema.get("default", "")
        if isinstance(value, bool):
            value = str(value).lower()
        variable = {
            "include_draft": "include_draft",
            "include_intermediate": "include_intermediate",
            "after": "history_after",
        }.get(name)
        entries.append(
            {
                "key": name,
                "value": "{{" + variable + "}}" if variable else str(value),
                "disabled": value == "",
                "description": parameter.get("description", name),
            }
        )
    return entries


def make_item(folder, method, path, name, operation):
    request_path = path
    for variable in ("asset_id", "sample_id", "run_id"):
        request_path = request_path.replace("{" + variable + "}", "{{" + variable + "}}")
    query = query_parameters(operation)
    if path.endswith("/events"):
        next(q for q in query if q["key"] == "after")["value"] = "{{sse_after}}"
    if method == "DELETE" and "/assets/" in path:
        request_path = request_path.replace("{{asset_id}}", "{{delete_asset_id}}")
    raw = "{{base_url}}" + request_path
    enabled = [q for q in query if not q["disabled"]]
    if enabled:
        raw += "?" + "&".join(q["key"] + "=" + q["value"] for q in enabled)
    request = {
        "method": method,
        "header": [],
        "url": {"raw": raw, "host": ["{{base_url}}"], "path": request_path.strip("/").split("/")},
        "description": f"{method} {path}\n\n"
        + operation.get("description", operation.get("summary", name)),
    }
    if query:
        request["url"]["query"] = query
    private = any("HTTPBearer" in rule for rule in operation.get("security", []))
    if not private:
        request["auth"] = {"type": "noauth"}
    if path == "/api/v1/operations/metrics":
        request["auth"] = {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{operations_token}}", "type": "string"}],
        }
    body = None
    if method == "POST" and path == "/api/v1/sessions":
        body = '{"label": {{session_label_json}}}'
    elif method == "POST" and path == "/api/v1/assets":
        request["body"] = {
            "mode": "formdata",
            "formdata": [
                {
                    "key": "file",
                    "type": "file",
                    "src": "",
                    "description": "Choose a JPEG/PNG/WebP in Postman; set enable_upload=true.",
                }
            ],
        }
    elif method == "POST" and path == "/api/v1/runs":
        body = '{"asset_id":"{{asset_id}}","question":{{question_json}},"audience":"{{audience}}","profile":"{{profile}}"}'
    elif method == "PUT" and path.endswith("/bookmark"):
        body = '{"saved": {{bookmark_saved}}}'
    elif method in {"POST", "PUT"} and path.endswith("/feedback"):
        body = '{"rating":"{{feedback_rating}}","note":{{feedback_note_json}}}'
    if body:
        request["body"] = {"mode": "raw", "raw": body, "options": {"raw": {"language": "json"}}}
        request["header"].append({"key": "Content-Type", "value": "application/json"})
    success = next(
        int(code) for code in operation["responses"] if code.isdigit() and 200 <= int(code) < 300
    )
    expected = [success]
    if path == "/health/ready":
        expected = [200, 503]
    if method == "DELETE" and "/assets/" in path:
        expected = [204, 409]
    before, after = (
        [],
        [
            f"pm.test('Expected HTTP status', () => pm.expect(pm.response.code).to.be.oneOf({json.dumps(expected)}));"
        ],
    )
    if private:
        before.append(
            "if (!pm.variables.get('access_token')) throw new Error('Run Create session first.');"
        )
    for variable in ("asset_id", "run_id"):
        if "{{" + variable + "}}" in request_path or (
            variable == "asset_id" and path == "/api/v1/runs" and method == "POST"
        ):
            before.append(
                f"if (!pm.variables.get('{variable}')) throw new Error('Missing {variable}; run the earlier setup requests.');"
            )
    if folder.startswith("10 "):
        before.insert(
            0,
            "if (String(pm.variables.get('run_lifecycle_actions')) !== 'true') pm.execution.skipRequest();",
        )
    if method == "POST" and path == "/api/v1/assets":
        before.insert(
            0,
            "if (String(pm.variables.get('enable_upload')) !== 'true') pm.execution.skipRequest();",
        )
    if method == "POST" and path == "/api/v1/sessions":
        before.append(
            "const bootstrap = pm.variables.get('bootstrap_token'); if (bootstrap) pm.request.headers.upsert({key:'X-Bootstrap-Token',value:bootstrap}); else pm.request.headers.remove('X-Bootstrap-Token');"
        )
        after.append("""
if (pm.response.code === 201) {
  const data = pm.response.json();
  pm.environment.set('access_token', data.access_token);
  pm.environment.set('session_id', data.session_id);
  ['asset_id','run_id','retry_run_id','idempotency_key','retry_idempotency_key','delete_asset_id'].forEach(key => pm.environment.unset(key));
  ['history_after','sse_after','last_event_id','_poll_attempts'].forEach(key => pm.environment.set(key, '0'));
}
""")
    if method == "POST" and (path.endswith("/assets") or path == "/api/v1/assets"):
        after.append(
            "if (pm.response.code === 201) pm.environment.set('asset_id', pm.response.json().asset_id);"
        )
    if method == "POST" and (path == "/api/v1/runs" or path.endswith("/retry")):
        key = "retry_idempotency_key" if path.endswith("/retry") else "idempotency_key"
        request["header"].append({"key": "Idempotency-Key", "value": "{{" + key + "}}"})
        before.append(
            f"if (!pm.variables.get('{key}')) pm.environment.set('{key}', "
            "pm.variables.replaceIn('{{$guid}}'));"
        )
        target = "retry_run_id" if path.endswith("/retry") else "run_id"
        after.append(
            f"if (pm.response.code === 202) {{ const id = pm.response.json().run_id; "
            f"if ('{target}' === 'run_id' && pm.environment.get('run_id') !== id) "
            "['history_after','sse_after','last_event_id'].forEach(key => pm.environment.set(key, '0')); "
            f"pm.environment.set('{target}', id); }}"
        )
        if target == "run_id":
            before.append("pm.environment.set('_poll_attempts', '0');")
            after.append(
                "if (pm.response.code === 202) { pm.environment.set('request_id', pm.response.json().request_id); pm.environment.set('trace_id', pm.response.json().trace_id); }"
            )
    if method == "GET" and path == "/api/v1/runs/{run_id}":
        after.append("""
if (pm.response.code === 200) {
  const state = pm.response.json().execution_status;
  if (['queued','running','cancel_requested'].includes(state)) {
    const count = Number(pm.environment.get('_poll_attempts') || 0) + 1;
    pm.environment.set('_poll_attempts', String(count));
    if (count >= Number(pm.variables.get('poll_max_attempts') || 120)) {
      pm.test('Polling budget exceeded', () => pm.expect.fail('Run still active; inspect status/events and increase poll_max_attempts.'));
      pm.execution.setNextRequest(null);
    } else {
      pm.execution.setNextRequest(pm.info.requestId);
      const delay = Math.min(10000, Math.max(100, Number(pm.variables.get('poll_interval_ms') || 1000)));
      setTimeout(() => {}, delay);
    }
  } else if (state !== 'succeeded') {
    pm.test('Run succeeded', () => pm.expect(state).to.eql('succeeded'));
    pm.execution.setNextRequest(null);
  }
}
""")
    if path.endswith("/events/history"):
        after.append(
            "if (pm.response.code === 200) pm.environment.set('history_after', String(pm.response.json().next_after));"
        )
    if path.endswith("/events"):
        request["header"].append({"key": "Accept", "value": "text/event-stream"})
        after.append(r"""
pm.test('SSE content type', () => pm.expect(pm.response.headers.get('Content-Type')).to.include('text/event-stream'));
const ids = Array.from(pm.response.text().matchAll(/^id:\s*(\d+)\s*$/gm), m => Number(m[1]));
if (ids.length) pm.environment.set('last_event_id', String(Math.max(...ids)));
""")
    if method == "DELETE" and "/assets/" in path:
        before.append(
            "if (!pm.variables.get('delete_asset_id')) pm.variables.set('delete_asset_id', pm.variables.get('asset_id'));"
        )
    if method == "DELETE" and path == "/api/v1/sessions/me":
        after.append(
            "if (pm.response.code === 204) ['access_token','session_id'].forEach(key => pm.environment.unset(key));"
        )
    if path == "/api/v1/operations/metrics":
        before.append("if (!pm.variables.get('operations_token')) pm.execution.skipRequest();")
        after.append(
            "pm.test('Prometheus text', () => pm.expect(pm.response.text()).to.include('heritage_runs'));"
        )
    events = [script("test", "\n".join(after))]
    if before:
        events.insert(0, script("prerequest", "\n".join(before)))
    return {
        "id": uid(method + " " + path),
        "name": name,
        "request": request,
        "event": events,
        "response": [],
    }


def build_collection(openapi):
    actual = {
        (method.upper(), path)
        for path, verbs in openapi["paths"].items()
        for method in verbs
        if method in {"get", "post", "put", "delete", "patch"}
    }
    intended = {(method, path) for _, method, path, _ in REQUESTS}
    if actual != intended:
        raise ValueError("API contract changed; update Postman request ordering before export")
    folders = {}
    for folder, method, path, name in REQUESTS:
        item = make_item(folder, method, path, name, openapi["paths"][path][method.lower()])
        folders.setdefault(folder, []).append(item)
        variant = None
        if path.endswith("/events"):
            variant = deepcopy(item)
            variant["name"] = "Replay SSE using Last-Event-ID"
            variant["request"]["header"].append(
                {"key": "Last-Event-ID", "value": "{{last_event_id}}"}
            )
        elif path.endswith("/result"):
            variant = deepcopy(item)
            variant["name"] = "Result including intermediate artifacts"
            variant["request"]["url"]["query"][0]["value"] = "true"
        elif path.endswith("/export"):
            variant = deepcopy(item)
            variant["name"] = "Export Markdown"
            next(q for q in variant["request"]["url"]["query"] if q["key"] == "format")["value"] = (
                "markdown"
            )
        if variant:
            variant["id"] = uid(variant["name"])
            query = [q for q in variant["request"]["url"].get("query", []) if not q["disabled"]]
            variant["request"]["url"]["raw"] = item["request"]["url"]["raw"].split("?")[0]
            if query:
                variant["request"]["url"]["raw"] += "?" + "&".join(
                    q["key"] + "=" + q["value"] for q in query
                )
            folders[folder].append(variant)
    return {
        "info": {
            "_postman_id": uid("collection"),
            "name": "Heritage VQA - Complete API",
            "schema": SCHEMA,
            "description": "31 API operations + SSE replay/intermediate/Markdown variants. Import an environment, run folders 01-09 in order. Tokens/asset_id/run_id are saved automatically. Optional upload requires choosing a file and enable_upload=true. Folder 10 requires run_lifecycle_actions=true and revokes the session last. See docs/postman.md. No real credentials are included.",
        },
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}],
        },
        "variable": [
            {"key": key, "value": value, "type": "string"} for key, value in DEFAULTS.items()
        ],
        "event": root_scripts(),
        "item": [{"name": name, "item": items} for name, items in folders.items()],
    }


def environment(name, url):
    return {
        "id": uid(name),
        "name": name,
        "_postman_variable_scope": "environment",
        "values": [
            {
                "key": key,
                "value": url if key == "base_url" else value,
                "type": "secret" if key in SECRET_KEYS else "default",
                "enabled": True,
            }
            for key, value in DEFAULTS.items()
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "postman")
    args = parser.parse_args()
    from api.main import app

    schema = app.openapi()
    artifacts = {
        "heritage-vqa.postman_collection.json": build_collection(schema),
        "heritage-vqa-demo.postman_environment.json": environment(
            "Heritage VQA - Demo", "http://127.0.0.1:8001"
        ),
        "heritage-vqa-local.postman_environment.json": environment(
            "Heritage VQA - Local API", "http://127.0.0.1:8000"
        ),
        "heritage-vqa.openapi.json": schema,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in artifacts.items():
        (args.output_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"Exported {len(artifacts)} credential-free JSON files; 31 operations / 34 requests.")


if __name__ == "__main__":
    main()
