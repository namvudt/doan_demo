"""Export complete Postman v2.1 artifacts from the application's OpenAPI contract."""

import argparse
import json
import re
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
    "heritage_id": "",
    "heritage_media_id": "",
    "heritage_version": "",
    "catalog_write_body": "",
    "run_id": "",
    "retry_run_id": "",
    "review_run_id": "",
    "clarification_run_id": "",
    "clarification_id": "",
    "clarification_revision": "1",
    "clarification_answer": "",
    "selected_candidate": "null",
    "clarification_idempotency_key": "",
    "region_id": "",
    "focus_box": "null",
    "location_hint": "null",
    "delete_asset_id": "",
    "question": "Những chi tiết kiến trúc nào nhìn thấy rõ trong ảnh?",
    "audience": "tourist",
    "profile": "default",
    "idempotency_key": "",
    "retry_idempotency_key": "",
    "review_idempotency_key": "",
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
    "enable_catalog_asset_import": "false",
    "enable_catalog_writes": "false",
    "enable_model_calls": "false",
    "allow_live_model_calls": "false",
    "live_model_consent": "false",
    "enable_accounts": "false",
    "enable_account_updates": "false",
    "enable_role_changes": "false",
    "enable_conversation_writes": "false",
    "enable_favorite_writes": "false",
    "enable_editorial_writes": "false",
    "enable_remote_ingest": "false",
    "enable_source_review": "false",
    "enable_source_publish": "false",
    "enable_media_writes": "false",
    "enable_destructive_actions": "false",
    "account_access_token": "",
    "editor_access_token": "",
    "admin_access_token": "",
    "refresh_token": "",
    "account_email": "",
    "account_password": "",
    "current_password": "",
    "new_password": "",
    "display_name": "",
    "account_id": "",
    "account_version": "1",
    "account_role": "user",
    "account_disabled": "false",
    "conversation_id": "",
    "conversation_title": "Postman conversation",
    "conversation_version": "1",
    "memory_enabled": "false",
    "source_id": "",
    "version_id": "",
    "source_version": "1",
    "source_title": "",
    "source_url": "",
    "source_text": "",
    "source_publisher": "",
    "source_review_attestation": "",
    "review_note": "",
    "entity_id": "",
    "parent_heritage_id": "null",
    "binding_note": "",
    "delete_run_id": "",
    "delete_media_id": "",
    "delete_conversation_id": "",
    "archive_heritage_id": "",
    "resume_idempotency_key": "",
    "can_resume": "false",
    "run_heritage_id": "null",
    "run_conversation_id": "null",
}
SECRET_KEYS = {
    "access_token",
    "bootstrap_token",
    "operations_token",
    "account_access_token",
    "editor_access_token",
    "admin_access_token",
    "refresh_token",
    "account_password",
    "current_password",
    "new_password",
}

# Ordering also provides a ready-to-run workflow, with optional actions last.
REQUESTS = [
    ("01 System", "GET", "/health/live", "Liveness"),
    ("01 System", "GET", "/health/ready", "Readiness"),
    ("01 System", "GET", "/api/v1/capabilities", "Capabilities and model mode"),
    ("01 System", "GET", "/api/v1/samples", "List sample images"),
    ("01 Catalog", "GET", "/api/v1/heritages", "List published heritages and save first ID"),
    ("01 Catalog", "GET", "/api/v1/heritages/{heritage_id}", "Published heritage detail"),
    (
        "01 Catalog",
        "GET",
        "/api/v1/heritages/{heritage_id}/media/{media_id}/content",
        "Published catalog image",
    ),
    ("02 Session", "POST", "/api/v1/sessions", "Create session and save access token"),
    ("02 Session", "GET", "/api/v1/sessions/me", "Current session"),
    ("03 Assets", "POST", "/api/v1/samples/{sample_id}/assets", "Create asset from sample"),
    ("03 Assets", "GET", "/api/v1/assets", "List assets"),
    ("03 Assets", "GET", "/api/v1/assets/{asset_id}", "Asset metadata"),
    ("03 Assets", "GET", "/api/v1/assets/{asset_id}/content", "Download normalized PNG"),
    ("03 Assets", "POST", "/api/v1/assets", "Upload image - optional"),
    (
        "03 Assets",
        "POST",
        "/api/v1/heritages/{heritage_id}/media/{media_id}/assets",
        "Import catalog image as owned asset - optional",
    ),
    ("04 Workflow", "GET", "/api/v1/workflow", "Workflow stages and diagram"),
    ("04 Workflow", "POST", "/api/v1/preflight", "Check role credentials and model metadata"),
    ("05 Runs", "POST", "/api/v1/runs", "Create run and save run ID"),
    ("05 Runs", "GET", "/api/v1/runs", "List runs"),
    ("05 Runs", "GET", "/api/v1/runs/{run_id}", "Wait for run - Runner polling"),
    ("06 Events", "GET", "/api/v1/runs/{run_id}/events/history", "Event history JSON"),
    ("06 Events", "GET", "/api/v1/runs/{run_id}/events", "Stream stages SSE"),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/result", "Final result"),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/sources", "Sources and citations"),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/evidence", "Claims and registered evidence"),
    (
        "07 Results",
        "GET",
        "/api/v1/runs/{run_id}/regions/{region_id}/image",
        "View evidence crop - optional",
    ),
    (
        "07 Results",
        "GET",
        "/api/v1/runs/{run_id}/clarification",
        "Pending clarification and revision",
    ),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/steps", "Intermediate stage snapshots"),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/metrics", "Durable model attempts and usage"),
    ("07 Results", "GET", "/api/v1/runs/{run_id}/export", "Export JSON"),
    ("08 Feedback", "PUT", "/api/v1/runs/{run_id}/bookmark", "Save bookmark"),
    ("08 Feedback", "POST", "/api/v1/runs/{run_id}/feedback", "Create feedback"),
    ("08 Feedback", "PUT", "/api/v1/runs/{run_id}/feedback", "Update feedback"),
    ("08 Feedback", "GET", "/api/v1/runs/{run_id}/feedback", "Read feedback"),
    ("09 Operations", "GET", "/api/v1/operations/metrics", "Prometheus metrics - operator token"),
    (
        "09 Operations",
        "POST",
        "/api/v1/operations/heritages",
        "Create heritage - optional operator write",
    ),
    (
        "09 Operations",
        "PUT",
        "/api/v1/operations/heritages/{heritage_id}",
        "Replace heritage with expected version - optional operator write",
    ),
    (
        "10 Lifecycle actions - optional",
        "POST",
        "/api/v1/runs/{run_id}/clarification",
        "Answer clarification - saves clarification_run_id",
    ),
    ("10 Lifecycle actions - optional", "POST", "/api/v1/runs/{run_id}/cancel", "Cancel run"),
    (
        "10 Lifecycle actions - optional",
        "POST",
        "/api/v1/runs/{run_id}/review",
        "Review only Judge - saves review_run_id",
    ),
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

PRODUCT_REQUESTS = [
    (
        "01 Catalog",
        "GET",
        "/api/v1/heritages/{heritage_id}/context",
        "Catalog context is an unverified hint",
    ),
    (
        "01 Catalog",
        "GET",
        "/api/v1/heritages/{heritage_id}/sources",
        "Published reviewed source excerpts",
    ),
    ("11 Accounts - opt in", "POST", "/api/v1/accounts", "Register account - explicit opt in"),
    ("11 Accounts - opt in", "POST", "/api/v1/auth/sessions", "Sign in and store account tokens"),
    ("11 Accounts - opt in", "GET", "/api/v1/users/me", "Account profile and effective role"),
    ("11 Accounts - opt in", "PATCH", "/api/v1/users/me", "Update account profile"),
    ("11 Accounts - opt in", "POST", "/api/v1/auth/refresh", "Rotate refresh token"),
    ("11 Accounts - opt in", "POST", "/api/v1/users/me/password", "Change account password"),
    (
        "11 Accounts - opt in",
        "PUT",
        "/api/v1/operations/accounts/{account_id}/role",
        "Assign role - existing admin or server operations",
    ),
    ("11 Accounts - opt in", "DELETE", "/api/v1/auth/sessions/current", "Sign out account session"),
    ("12 Conversations - opt in", "POST", "/api/v1/conversations", "Create owned conversation"),
    ("12 Conversations - opt in", "GET", "/api/v1/conversations", "List owned conversations"),
    (
        "12 Conversations - opt in",
        "GET",
        "/api/v1/conversations/{conversation_id}",
        "Conversation detail",
    ),
    (
        "12 Conversations - opt in",
        "PATCH",
        "/api/v1/conversations/{conversation_id}",
        "Update conversation at expected revision",
    ),
    (
        "12 Conversations - opt in",
        "GET",
        "/api/v1/conversations/{conversation_id}/messages",
        "Persisted conversation turns",
    ),
    (
        "12 Conversations - opt in",
        "GET",
        "/api/v1/conversations/{conversation_id}/memory",
        "Bounded unverified conversation memory",
    ),
    (
        "12 Conversations - opt in",
        "DELETE",
        "/api/v1/conversations/{conversation_id}/memory",
        "Forget prior conversation memory",
    ),
    (
        "12 Conversations - opt in",
        "DELETE",
        "/api/v1/conversations/{conversation_id}",
        "Delete explicitly selected conversation",
    ),
    (
        "12 Conversations - opt in",
        "GET",
        "/api/v1/users/me/heritage-favorites",
        "List account heritage favorites",
    ),
    (
        "12 Conversations - opt in",
        "PUT",
        "/api/v1/users/me/heritage-favorites/{heritage_id}",
        "Favorite a heritage idempotently",
    ),
    (
        "12 Conversations - opt in",
        "DELETE",
        "/api/v1/users/me/heritage-favorites/{heritage_id}",
        "Remove heritage favorite",
    ),
    (
        "13 Editorial - opt in",
        "GET",
        "/api/v1/operations/content-sources",
        "List editorial sources",
    ),
    (
        "13 Editorial - opt in",
        "POST",
        "/api/v1/operations/content-sources",
        "Create an immutable draft source",
    ),
    (
        "13 Editorial - opt in",
        "POST",
        "/api/v1/operations/content-sources/ingest",
        "Fetch allowlisted URL into a draft",
    ),
    (
        "13 Editorial - opt in",
        "GET",
        "/api/v1/operations/content-sources/{source_id}",
        "Read source revisions for human review",
    ),
    (
        "13 Editorial - opt in",
        "POST",
        "/api/v1/operations/content-sources/{source_id}/versions",
        "Add source revision",
    ),
    (
        "13 Editorial - opt in",
        "POST",
        "/api/v1/operations/content-sources/{source_id}/versions/{version_id}/review",
        "Record explicit human source review",
    ),
    (
        "13 Editorial - opt in",
        "POST",
        "/api/v1/operations/content-sources/{source_id}/versions/{version_id}/publish",
        "Publish reviewed version",
    ),
    (
        "13 Editorial - opt in",
        "POST",
        "/api/v1/operations/content-sources/{source_id}/versions/{version_id}/withdraw",
        "Withdraw explicitly selected publication",
    ),
    (
        "13 Editorial - opt in",
        "PUT",
        "/api/v1/operations/heritages/{heritage_id}/entity-binding",
        "Bind catalog to canonical entity",
    ),
    (
        "13 Editorial - opt in",
        "GET",
        "/api/v1/operations/heritages/{heritage_id}/audit",
        "Read editorial audit history",
    ),
    (
        "13 Editorial - opt in",
        "POST",
        "/api/v1/operations/heritages/{heritage_id}/media",
        "Upload catalog image",
    ),
    (
        "13 Editorial - opt in",
        "PUT",
        "/api/v1/operations/heritages/{heritage_id}/media/{media_id}",
        "Replace catalog image",
    ),
    (
        "13 Editorial - opt in",
        "DELETE",
        "/api/v1/operations/heritages/{heritage_id}/media/{media_id}",
        "Delete explicitly selected catalog image",
    ),
    (
        "13 Editorial - opt in",
        "POST",
        "/api/v1/operations/heritages/{heritage_id}/archive",
        "Archive explicitly selected heritage",
    ),
    (
        "14 Recovery and deletion - opt in",
        "GET",
        "/api/v1/runs/{run_id}/recovery",
        "Completed checkpoints and resume eligibility",
    ),
    (
        "14 Recovery and deletion - opt in",
        "POST",
        "/api/v1/runs/{run_id}/resume",
        "Resume interrupted worker run",
    ),
    (
        "14 Recovery and deletion - opt in",
        "DELETE",
        "/api/v1/runs/{run_id}",
        "Soft-delete explicitly selected run",
    ),
]
PRODUCT_KEYS = {(method, path) for _, method, path, _ in PRODUCT_REQUESTS}
guest_teardown = next(item for item in REQUESTS if item[1:3] == ("DELETE", "/api/v1/sessions/me"))
account_teardown = next(
    item for item in PRODUCT_REQUESTS if item[1:3] == ("DELETE", "/api/v1/auth/sessions/current")
)
REQUESTS = [item for item in REQUESTS if item is not guest_teardown]
REQUESTS += [item for item in PRODUCT_REQUESTS if item is not account_teardown]
REQUESTS += [
    ("15 Session teardown - opt in", *account_teardown[1:]),
    ("15 Session teardown - opt in", *guest_teardown[1:]),
]


def model_guard():
    return r"""
if (String(pm.variables.get('enable_model_calls')) !== 'true') pm.execution.skipRequest();
try {
  const response = await pm.sendRequest({url: String(pm.variables.get('base_url')).replace(/\/+$/, '') + '/api/v1/capabilities', method:'GET', auth:{type:'noauth'}});
  if (response.code !== 200) pm.execution.skipRequest();
  const caps = response.json();
  const liveAllowed = String(pm.variables.get('allow_live_model_calls')) === 'true' && String(pm.variables.get('live_model_consent')) === 'true';
  if (caps.model_mode !== 'demo' && !(caps.model_mode === 'live' && liveAllowed && caps.model_configured && caps.missing_roles.length === 0)) pm.execution.skipRequest();
} catch (_) { pm.execution.skipRequest(); }
"""


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
['question', 'feedback_note', 'session_label', 'clarification_answer', 'account_email', 'account_password', 'display_name', 'current_password', 'new_password', 'conversation_title', 'source_title', 'source_url', 'source_text', 'source_publisher', 'source_review_attestation', 'review_note', 'entity_id', 'binding_note', 'account_role'].forEach(key => {
  pm.variables.set(key + '_json', JSON.stringify(String(pm.variables.get(key) || '')));
});
pm.variables.set('editorial_token', pm.variables.get('editor_access_token') || pm.variables.get('operations_token') || '');
pm.variables.set('role_token', pm.variables.get('admin_access_token') || pm.variables.get('operations_token') || '');
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
        if value is None:
            value = ""
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
    if (method, path) in PRODUCT_KEYS:
        return make_product_item(folder, method, path, name, operation)
    request_path = path
    for variable in ("asset_id", "sample_id", "run_id", "heritage_id", "region_id"):
        request_path = request_path.replace("{" + variable + "}", "{{" + variable + "}}")
    request_path = request_path.replace("{media_id}", "{{heritage_media_id}}")
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
    operator = any("OperationsBearer" in rule for rule in operation.get("security", []))
    editor_account = any("AccountBearer" in rule for rule in operation.get("security", []))
    operator_variable = "editorial_token" if editor_account else "operations_token"
    if operator:
        request["auth"] = {
            "type": "bearer",
            "bearer": [
                {"key": "token", "value": "{{" + operator_variable + "}}", "type": "string"}
            ],
        }
    body = None
    if method == "POST" and path == "/api/v1/sessions":
        body = '{"label": {{session_label_json}}}'
    elif method == "POST" and path == "/api/v1/preflight":
        body = '{"roles":["coordinator","visual","aggregator","judge"],"force":false}'
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
        body = '{"asset_id":"{{asset_id}}","question":{{question_json}},"audience":"{{audience}}","profile":"{{profile}}","focus_box":{{focus_box}},"location_hint":{{location_hint}},"heritage_id":{{run_heritage_id}},"conversation_id":{{run_conversation_id}}}'
    elif method == "POST" and path.endswith("/clarification"):
        body = '{"clarification_id":"{{clarification_id}}","revision":{{clarification_revision}},"answer":{{clarification_answer_json}},"selected_candidate":{{selected_candidate}}}'
    elif method == "PUT" and path.endswith("/bookmark"):
        body = '{"saved": {{bookmark_saved}}}'
    elif method in {"POST", "PUT"} and path.endswith("/feedback"):
        body = '{"rating":"{{feedback_rating}}","note":{{feedback_note_json}}}'
    elif operator and method in {"POST", "PUT"}:
        body = "{{catalog_write_body}}"
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
    for variable in ("heritage_id", "heritage_media_id"):
        if "{{" + variable + "}}" in request_path:
            before.append(f"if (!pm.variables.get('{variable}')) pm.execution.skipRequest();")
    if operator and method in {"POST", "PUT"}:
        before.insert(
            0,
            "if (String(pm.variables.get('enable_catalog_writes')) !== 'true') pm.execution.skipRequest();",
        )
        before.append(
            "if (String(pm.variables.get('enable_catalog_writes')) === 'true' && pm.variables.get('operations_token') && !pm.variables.get('catalog_write_body')) throw new Error('Set catalog_write_body to a full HeritageWrite JSON; PUT requires the current version.');"
        )
        after.append(
            "if ([200,201].includes(pm.response.code)) { const data = pm.response.json(); pm.environment.set('heritage_id', data.heritage_id); pm.environment.set('heritage_version', String(data.version)); }"
        )
    if path == "/api/v1/heritages":
        after.append("""
if (pm.response.code === 200 && !pm.variables.get('heritage_id')) {
  const first = pm.response.json().items[0];
  if (first) {
    pm.environment.set('heritage_id', first.heritage_id);
    pm.environment.set('heritage_version', String(first.version));
    if (first.media[0]) pm.environment.set('heritage_media_id', first.media[0].media_id);
  }
}
""")
    if path == "/api/v1/heritages/{heritage_id}":
        after.append("""
if (pm.response.code === 200) {
  const data = pm.response.json();
  pm.environment.set('heritage_version', String(data.version));
  if (data.media[0]) pm.environment.set('heritage_media_id', data.media[0].media_id);
}
""")
    if method == "POST" and path == "/api/v1/heritages/{heritage_id}/media/{media_id}/assets":
        before.insert(
            0,
            "if (String(pm.variables.get('enable_catalog_asset_import')) !== 'true') pm.execution.skipRequest();",
        )
    for variable in ("asset_id", "run_id"):
        if "{{" + variable + "}}" in request_path or (
            variable == "asset_id" and path == "/api/v1/runs" and method == "POST"
        ):
            before.append(f"if (!pm.variables.get('{variable}')) pm.execution.skipRequest();")
    if folder.startswith(("10 ", "15 ")):
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
  ['asset_id','run_id','retry_run_id','review_run_id','clarification_run_id','clarification_id','region_id','idempotency_key','retry_idempotency_key','review_idempotency_key','clarification_idempotency_key','delete_asset_id'].forEach(key => pm.environment.unset(key));
  ['history_after','sse_after','last_event_id','_poll_attempts'].forEach(key => pm.environment.set(key, '0'));
}
""")
    if method == "POST" and (path.endswith("/assets") or path == "/api/v1/assets"):
        after.append(
            "if (pm.response.code === 201) pm.environment.set('asset_id', pm.response.json().asset_id);"
        )
    if method == "POST" and (
        path == "/api/v1/runs" or path.endswith(("/retry", "/review", "/clarification"))
    ):
        action = next(
            (name for name in ("review", "retry", "clarification") if path.endswith("/" + name)), ""
        )
        key = f"{action}_idempotency_key" if action else "idempotency_key"
        request["header"].append({"key": "Idempotency-Key", "value": "{{" + key + "}}"})
        before.append(
            f"if (!pm.variables.get('{key}')) pm.environment.set('{key}', "
            "pm.variables.replaceIn('{{$guid}}'));"
        )
        target = f"{action}_run_id" if action else "run_id"
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
  } else if (!['succeeded', 'awaiting_input'].includes(state)) {
    pm.test('Run succeeded', () => pm.expect(state).to.eql('succeeded'));
    pm.execution.setNextRequest(null);
  }
}
""")
    if path.endswith("/evidence"):
        after.append(
            "if (pm.response.code === 200) pm.environment.set('region_id', (pm.response.json().regions[0] || {}).region_id || '');"
        )
    if "/regions/" in path:
        before.insert(0, "if (!pm.variables.get('region_id')) pm.execution.skipRequest();")
    if path.endswith("/clarification") and method == "GET":
        after.append("""
if (pm.response.code === 200) {
  const pending = pm.response.json().clarification;
  pm.environment.set('clarification_id', pending ? pending.clarification_id : '');
  pm.environment.set('clarification_revision', String(pending ? pending.revision : 1));
}
""")
    if path.endswith("/clarification") and method == "POST":
        before.insert(
            0,
            "if (!pm.variables.get('clarification_id') || !pm.variables.get('clarification_answer')) pm.execution.skipRequest();",
        )
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
        after.append(
            "pm.test('Prometheus text', () => pm.expect(pm.response.text()).to.include('heritage_runs'));"
        )
    if operator:
        before.insert(
            0, f"if (!pm.variables.get('{operator_variable}')) pm.execution.skipRequest();"
        )
    if method == "DELETE":
        before.insert(
            0,
            "if (String(pm.variables.get('enable_destructive_actions')) !== 'true') pm.execution.skipRequest();",
        )
    if method == "POST" and (
        path == "/api/v1/runs" or path.endswith(("/retry", "/review", "/clarification"))
    ):
        before.append(model_guard())
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


def make_product_item(folder, method, path, name, operation):
    request_path = re.sub(r"\{([a-z_]+)\}", lambda m: "{{" + m[1] + "}}", path)
    request_path = request_path.replace("{{media_id}}", "{{heritage_media_id}}")
    destructive_variables = {}
    if method == "DELETE" and path == "/api/v1/runs/{run_id}":
        destructive_variables["run_id"] = "delete_run_id"
    if method == "DELETE" and path == "/api/v1/conversations/{conversation_id}":
        destructive_variables["conversation_id"] = "delete_conversation_id"
    if method == "DELETE" and "/media/{media_id}" in path:
        destructive_variables["heritage_media_id"] = "delete_media_id"
    if path.endswith("/archive"):
        destructive_variables["heritage_id"] = "archive_heritage_id"
    for original, variable in destructive_variables.items():
        request_path = request_path.replace("{{" + original + "}}", "{{" + variable + "}}")
    query = query_parameters(operation)
    for entry in query:
        if entry["key"] == "version":
            entry.update(value="{{heritage_version}}", disabled=False)
    request = {
        "method": method,
        "header": [],
        "url": {
            "raw": "{{base_url}}" + request_path,
            "host": ["{{base_url}}"],
            "path": request_path.strip("/").split("/"),
        },
        "description": f"{method} {path}\n\n"
        + operation.get("description", operation.get("summary", name)),
    }
    if query:
        request["url"]["query"] = query
        enabled = [entry for entry in query if not entry["disabled"]]
        if enabled:
            request["url"]["raw"] += "?" + "&".join(
                entry["key"] + "=" + entry["value"] for entry in enabled
            )
    before, after = [], []
    operator = path.startswith("/api/v1/operations/")
    editorial = operator and not path.startswith("/api/v1/operations/accounts/")
    account = path.startswith("/api/v1/users/") or path == "/api/v1/auth/sessions/current"
    public = not operation.get("security")
    if public:
        request["auth"] = {"type": "noauth"}
    elif operator or account:
        variable = (
            "editorial_token" if editorial else "role_token" if operator else "account_access_token"
        )
        request["auth"] = {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{" + variable + "}}", "type": "string"}],
        }
        before.append(f"if (!pm.variables.get('{variable}')) pm.execution.skipRequest();")
    else:
        before.append("if (!pm.variables.get('access_token')) pm.execution.skipRequest();")
    for variable in re.findall(r"\{\{([a-z_]+)\}\}", request_path):
        before.append(f"if (!pm.variables.get('{variable}')) pm.execution.skipRequest();")
    flags = []
    if path.startswith("/api/v1/auth/") or path == "/api/v1/accounts":
        flags.append("enable_accounts")
    if (
        path.startswith("/api/v1/users/me")
        and method not in {"GET"}
        and "heritage-favorites" not in path
    ):
        flags.append("enable_account_updates")
    if path.startswith("/api/v1/operations/accounts/"):
        flags.append("enable_role_changes")
    if path.startswith("/api/v1/conversations") and method != "GET":
        flags.append("enable_conversation_writes")
    if "heritage-favorites" in path and method != "GET":
        flags.append("enable_favorite_writes")
    if editorial and method != "GET":
        flags.append("enable_editorial_writes")
    if path.endswith("/ingest"):
        flags.append("enable_remote_ingest")
    if path.endswith("/review"):
        flags.append("enable_source_review")
    if path.endswith("/publish"):
        flags.append("enable_source_publish")
    if "/media" in path and method != "GET":
        flags.append("enable_media_writes")
    if method == "DELETE" or path.endswith(("/archive", "/withdraw")):
        flags.append("enable_destructive_actions")
    if path.endswith("/resume"):
        flags.append("run_lifecycle_actions")
    before[:0] = [
        f"if (String(pm.variables.get('{flag}')) !== 'true') pm.execution.skipRequest();"
        for flag in flags
    ]
    body = None
    if path == "/api/v1/accounts":
        body = '{"email":{{account_email_json}},"display_name":{{display_name_json}},"password":{{account_password_json}}}'
    elif path == "/api/v1/auth/sessions":
        body = '{"email":{{account_email_json}},"password":{{account_password_json}}}'
    elif path == "/api/v1/auth/refresh":
        body = '{"refresh_token":"{{refresh_token}}"}'
        before.append("if (!pm.variables.get('refresh_token')) pm.execution.skipRequest();")
    elif path == "/api/v1/users/me" and method == "PATCH":
        body = '{"version":{{account_version}},"display_name":{{display_name_json}}}'
    elif path.endswith("/password"):
        body = '{"current_password":{{current_password_json}},"new_password":{{new_password_json}}}'
    elif path.startswith("/api/v1/operations/accounts/"):
        body = '{"version":{{account_version}},"role":{{account_role_json}},"disabled":{{account_disabled}}}'
    elif path == "/api/v1/conversations" and method == "POST":
        body = '{"title":{{conversation_title_json}},"memory_enabled":{{memory_enabled}}}'
    elif path == "/api/v1/conversations/{conversation_id}" and method == "PATCH":
        body = '{"version":{{conversation_version}},"title":{{conversation_title_json}},"memory_enabled":{{memory_enabled}}}'
    elif path == "/api/v1/operations/content-sources" and method == "POST":
        body = '{"heritage_id":"{{heritage_id}}","title":{{source_title_json}},"url":{{source_url_json}},"publisher":{{source_publisher_json}},"text":{{source_text_json}}}'
    elif path.endswith("/ingest"):
        body = '{"heritage_id":"{{heritage_id}}","url":{{source_url_json}},"title":{{source_title_json}}}'
    elif path.endswith("/versions"):
        body = '{"version":{{source_version}},"text":{{source_text_json}}}'
    elif path.endswith("/review"):
        before.append(
            "if (pm.variables.get('source_review_attestation') !== 'reviewed_against_source') pm.execution.skipRequest();"
        )
        body = '{"version":{{source_version}},"attestation":{{source_review_attestation_json}},"note":{{review_note_json}}}'
    elif path.endswith(("/publish", "/withdraw")):
        body = '{"version":{{source_version}}}'
    elif path.endswith("/entity-binding"):
        body = '{"version":{{heritage_version}},"entity_id":{{entity_id_json}},"parent_heritage_id":{{parent_heritage_id}},"note":{{binding_note_json}}}'
    elif path.endswith("/archive"):
        body = '{"version":{{heritage_version}}}'
    elif "/media" in path and method in {"POST", "PUT"}:
        request["body"] = {
            "mode": "formdata",
            "formdata": [
                {
                    "key": "file",
                    "type": "file",
                    "src": "",
                    "description": "Choose a JPEG/PNG/WebP; uploaded copy is normalized.",
                },
                {"key": "version", "type": "text", "value": "{{heritage_version}}"},
            ],
        }
    if body is not None:
        request["body"] = {"mode": "raw", "raw": body, "options": {"raw": {"language": "json"}}}
        request["header"].append({"key": "Content-Type", "value": "application/json"})
    if path.endswith("/resume"):
        before.append(
            "if (String(pm.variables.get('can_resume')) !== 'true') pm.execution.skipRequest();"
        )
        before.append(
            "if (!pm.variables.get('resume_idempotency_key')) pm.environment.set('resume_idempotency_key', pm.variables.replaceIn('{{$guid}}'));"
        )
        before.append(model_guard())
        request["header"].append({"key": "Idempotency-Key", "value": "{{resume_idempotency_key}}"})
    success = next(
        int(code) for code in operation["responses"] if code.isdigit() and 200 <= int(code) < 300
    )
    after.append(
        f"pm.test('Expected HTTP status', () => pm.expect(pm.response.code).to.equal({success}));"
    )
    if path in {"/api/v1/auth/sessions", "/api/v1/auth/refresh"}:
        after.append(
            "if (pm.response.code === 200) { const d=pm.response.json(); pm.environment.set('account_access_token',d.access_token); pm.environment.set('refresh_token',d.refresh_token); pm.environment.set('account_id',d.account.account_id); pm.environment.set('account_version',String(d.account.version)); }"
        )
    if (
        path == "/api/v1/accounts"
        or (path == "/api/v1/users/me" and method in {"GET", "PATCH"})
        or path.startswith("/api/v1/operations/accounts/")
    ):
        after.append(
            "if ([200,201].includes(pm.response.code)) { const d=pm.response.json(); pm.environment.set('account_id',d.account_id); pm.environment.set('account_version',String(d.version)); }"
        )
    if path.startswith("/api/v1/conversations") and method in {"POST", "PATCH"}:
        after.append(
            "if ([200,201].includes(pm.response.code)) { const d=pm.response.json(); pm.environment.set('conversation_id',d.conversation_id); pm.environment.set('conversation_version',String(d.version)); }"
        )
    if (
        path.startswith("/api/v1/operations/content-sources")
        and method in {"POST", "GET"}
        and "{source_id}" in path
        or (
            path
            in {"/api/v1/operations/content-sources", "/api/v1/operations/content-sources/ingest"}
            and method == "POST"
        )
    ):
        after.append(
            "if ([200,201].includes(pm.response.code)) { const d=pm.response.json(); if(d.source_id) { pm.environment.set('source_id',d.source_id); pm.environment.set('source_version',String(d.version)); if(d.versions[0])pm.environment.set('version_id',d.versions[0].version_id); } }"
        )
    if path.endswith("/recovery"):
        after.append(
            "if(pm.response.code===200)pm.environment.set('can_resume',String(pm.response.json().can_resume));"
        )
    if "/media" in path and method in {"POST", "PUT"}:
        after.append(
            "if([200,201].includes(pm.response.code)) { const d=pm.response.json(); pm.environment.set('heritage_media_id',d.media_id); pm.environment.set('heritage_version',String(d.heritage_version)); }"
        )
    if path.endswith("/entity-binding"):
        after.append(
            "if(pm.response.code===200)pm.environment.set('heritage_version',String(pm.response.json().heritage_version));"
        )
    return {
        "id": uid(method + " " + path),
        "name": name,
        "request": request,
        "event": [script("prerequest", "\n".join(before)), script("test", "\n".join(after))],
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
            "description": f"{len(REQUESTS)} API operations plus SSE replay/intermediate/Markdown variants. Default flags disable model calls, account creation/updates, editorial writes/review/publication, media writes, role assignment and destructive actions. Model-producing requests recheck live capabilities; live calls additionally require allow_live_model_calls=true AND live_model_consent=true. Source review additionally requires explicit reviewed_against_source attestation. DELETE/archive/withdraw require enable_destructive_actions=true and deletion targets are separate blank variables. Editorial auth accepts editor_access_token or server operations_token; role assignment requires admin_access_token or server operations_token. Session teardown runs last in folder15. Read docs/postman.md for per-feature setup. Templates contain no credentials or passwords.",
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
    parser.add_argument(
        "--include-openapi",
        action="store_true",
        help="Also generate the optional OpenAPI JSON (not tracked in Git)",
    )
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
    }
    if args.include_openapi:
        artifacts["heritage-vqa.openapi.json"] = schema
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in artifacts.items():
        (args.output_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        f"Exported {len(artifacts)} credential-free JSON files; {len(REQUESTS)} operations / {sum(len(folder['item']) for folder in artifacts['heritage-vqa.postman_collection.json']['item'])} requests."
    )


if __name__ == "__main__":
    main()
