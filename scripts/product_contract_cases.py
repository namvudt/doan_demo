"""Product/editorial HTTP cases for the runner's isolated synthetic demo database."""

import secrets
import time
from io import BytesIO
from uuid import uuid4

from PIL import Image
from sqlalchemy import select

from api.database import Database
from api.models import Run


def exercise_product(report, bootstrap, operations_token, database_url):
    from scripts.api_contract_report import require

    call = report.call
    operator = {"Authorization": "Bearer " + operations_token}
    email, password = "contract-" + uuid4().hex + "@example.test", secrets.token_urlsafe(24)
    _, account = call(
        "Create isolated ordinary account",
        "POST",
        "/api/v1/accounts",
        201,
        json={"email": email, "password": password, "display_name": "Synthetic HTTP editor"},
        check=lambda p: require(p["role"] == "user", "Registration must not grant an editor role"),
    )
    _, signed = call(
        "Sign in isolated account",
        "POST",
        "/api/v1/auth/sessions",
        json={"email": email, "password": password},
    )
    auth = {"Authorization": "Bearer " + signed["access_token"]}
    call("Account profile", "GET", "/api/v1/users/me", headers=auth)
    _, account = call(
        "Update account profile at expected version",
        "PATCH",
        "/api/v1/users/me",
        headers=auth,
        json={"display_name": "Synthetic HTTP reviewer", "version": account["version"]},
    )
    old_refresh = signed["refresh_token"]
    _, signed = call(
        "Rotate isolated refresh token",
        "POST",
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    auth = {"Authorization": "Bearer " + signed["access_token"]}
    call(
        "Old refresh token cannot be reused",
        "POST",
        "/api/v1/auth/refresh",
        401,
        json={"refresh_token": old_refresh},
    )
    call(
        "Ordinary account cannot assign own role",
        "PUT",
        f"/api/v1/operations/accounts/{account['account_id']}/role",
        403,
        headers=auth,
        json={"version": account["version"], "role": "admin"},
    )
    _, account = call(
        "Operator authorizes only isolated fixture editor",
        "PUT",
        f"/api/v1/operations/accounts/{account['account_id']}/role",
        headers=operator,
        json={"version": account["version"], "role": "editor"},
    )
    _, account = call(
        "Operator bootstraps isolated fixture admin",
        "PUT",
        f"/api/v1/operations/accounts/{account['account_id']}/role",
        headers=operator,
        json={"version": account["version"], "role": "admin"},
    )
    _, account_b = call(
        "Register second ordinary account for admin-role check",
        "POST",
        "/api/v1/accounts",
        201,
        json={
            "email": "second-" + email,
            "password": secrets.token_urlsafe(24),
            "display_name": "Synthetic second account",
        },
    )
    call(
        "DB-verified admin can assign another account's role",
        "PUT",
        f"/api/v1/operations/accounts/{account_b['account_id']}/role",
        headers=auth,
        json={"version": account_b["version"], "role": "editor"},
        check=lambda p: require(p["role"] == "editor", "Admin role change failed"),
    )
    site_id = "product-contract-site"
    _, site = call(
        "Editor account can create catalog record",
        "POST",
        "/api/v1/operations/heritages",
        201,
        headers=auth,
        json={
            "heritage_id": site_id,
            "slug": site_id,
            "name": "Văn Miếu — synthetic contract fixture",
            "category": "temple",
            "content_status": "published",
            "illustrative": True,
        },
    )
    public = f"/api/v1/heritages/{site_id}"
    editorial = f"/api/v1/operations/heritages/{site_id}"
    call(
        "Account favorites start empty",
        "GET",
        "/api/v1/users/me/heritage-favorites",
        headers=auth,
        check=lambda p: require(p["total"] == 0, "Unexpected favorite"),
    )
    call(
        "Favorite heritage idempotently",
        "PUT",
        f"/api/v1/users/me/heritage-favorites/{site_id}",
        headers=auth,
    )
    call(
        "Repeated favorite does not duplicate",
        "PUT",
        f"/api/v1/users/me/heritage-favorites/{site_id}",
        headers=auth,
    )
    call(
        "Read heritage favorites",
        "GET",
        "/api/v1/users/me/heritage-favorites",
        headers=auth,
        check=lambda p: require(p["total"] == 1, "Favorite duplicated"),
    )
    call(
        "Remove isolated favorite",
        "DELETE",
        f"/api/v1/users/me/heritage-favorites/{site_id}",
        204,
        headers=auth,
    )
    source_base = "/api/v1/operations/content-sources"
    text = "Văn Miếu: nguồn tổng hợp chỉ để kiểm tra hợp đồng HTTP; không phải dữ kiện lịch sử đã được nghiệm thu."
    _, document = call(
        "Create immutable draft source",
        "POST",
        source_base,
        201,
        headers=auth,
        json={
            "heritage_id": site_id,
            "title": "Văn Miếu — synthetic source",
            "url": "https://vanmieu.gov.vn/contract-fixture",
            "publisher": "Synthetic contract fixture",
            "text": text,
        },
    )
    source_path = source_base + "/" + document["source_id"]
    version_id = document["versions"][0]["version_id"]
    call(
        "List editorial sources", "GET", source_base, headers=auth, params={"heritage_id": site_id}
    )
    call("Read immutable source revision", "GET", source_path, headers=auth)
    call(
        "Draft source is not public evidence",
        "GET",
        public + "/sources",
        check=lambda p: require(p["items"] == [], "Draft was published without review"),
    )
    call(
        "Publishing a draft is rejected",
        "POST",
        source_path + f"/versions/{version_id}/publish",
        409,
        headers=auth,
        json={"version": 1},
    )
    _, document = call(
        "Explicit review of synthetic fixture text",
        "POST",
        source_path + f"/versions/{version_id}/review",
        headers=auth,
        json={
            "version": 1,
            "attestation": "reviewed_against_source",
            "note": "Reviewed only as a synthetic contract fixture, no historical accuracy claim.",
        },
    )
    _, document = call(
        "Publish reviewed synthetic fixture",
        "POST",
        source_path + f"/versions/{version_id}/publish",
        headers=auth,
        json={"version": document["version"]},
    )
    call(
        "Published source has immutable hash and reviewer",
        "GET",
        public + "/sources",
        check=lambda p: require(
            len(p["items"]) == 1 and p["items"][0]["reviewer"] == account["account_id"],
            "Publication provenance missing",
        ),
    )
    _, document = call(
        "Add separate draft revision",
        "POST",
        source_path + "/versions",
        201,
        headers=auth,
        json={
            "version": document["version"],
            "text": text + " This is a later synthetic revision.",
        },
    )
    second_id = document["versions"][0]["version_id"]
    _, document = call(
        "Review second synthetic revision",
        "POST",
        source_path + f"/versions/{second_id}/review",
        headers=auth,
        json={
            "version": document["version"],
            "attestation": "reviewed_against_source",
            "note": "Synthetic fixture review verifies revision workflow only.",
        },
    )
    _, document = call(
        "Publish second revision and retain old text",
        "POST",
        source_path + f"/versions/{second_id}/publish",
        headers=auth,
        json={"version": document["version"]},
        check=lambda p: require(
            [v["status"] for v in p["versions"]] == ["published", "archived"],
            "Source revision replacement failed",
        ),
    )
    call(
        "Withdraw isolated source publication",
        "POST",
        source_path + f"/versions/{second_id}/withdraw",
        headers=auth,
        json={"version": document["version"]},
    )
    call(
        "Source withdrawal removes public evidence",
        "GET",
        public + "/sources",
        check=lambda p: require(p["items"] == [], "Withdrawn publication remained public"),
    )
    call(
        "Ingestion blocks private URL without fetching Internet",
        "POST",
        source_base + "/ingest",
        422,
        headers=auth,
        json={"heritage_id": site_id, "url": "http://127.0.0.1/private"},
    )
    _, context = call(
        "Bind explicit canonical entity",
        "PUT",
        editorial + "/entity-binding",
        headers=auth,
        json={
            "version": site["version"],
            "entity_id": "hanoi:van-mieu",
            "note": "Synthetic binding, never visual proof.",
        },
    )
    call(
        "Canonical context stays an unverified hint",
        "GET",
        public + "/context",
        check=lambda p: require(
            p["canonical_entity_id"] == "hanoi:van-mieu"
            and p["location_hint"]["provenance"] == "user",
            "Catalog selection became evidence",
        ),
    )
    image = BytesIO()
    Image.new("RGB", (40, 30), "green").save(image, format="PNG")
    files = {"file": ("fixture.png", image.getvalue(), "image/png")}
    _, media = call(
        "Upload editor-owned catalog image",
        "POST",
        editorial + "/media",
        201,
        headers=auth,
        data={"version": str(context["heritage_version"])},
        files=files,
    )
    media_path = editorial + "/media/" + media["media_id"]
    call(
        "Public uploaded image decodes", "GET", public + "/media/" + media["media_id"] + "/content"
    )
    _, media = call(
        "Replace catalog image at expected revision",
        "PUT",
        media_path,
        headers=auth,
        data={"version": str(media["heritage_version"])},
        files=files,
    )
    call(
        "Remove isolated catalog upload",
        "DELETE",
        media_path,
        204,
        headers=auth,
        params={"version": media["heritage_version"]},
    )
    call(
        "Editorial history is attributable",
        "GET",
        editorial + "/audit",
        headers=auth,
        check=lambda p: require(
            any(e["action"] == "source.review" for e in p["items"]), "Missing editorial audit"
        ),
    )
    _, conversation = call(
        "Create owned conversation with opt-in memory",
        "POST",
        "/api/v1/conversations",
        201,
        headers=auth,
        json={"title": "Synthetic contract conversation", "memory_enabled": True},
    )
    conversation_path = "/api/v1/conversations/" + conversation["conversation_id"]
    call("List account conversations", "GET", "/api/v1/conversations", headers=auth)
    call("Read owned conversation", "GET", conversation_path, headers=auth)
    _, conversation = call(
        "Patch owned conversation",
        "PATCH",
        conversation_path,
        headers=auth,
        json={"version": conversation["version"], "title": "Updated synthetic conversation"},
    )
    _, asset = call(
        "Account creates own sample asset",
        "POST",
        "/api/v1/samples/chua_mot_cot/assets",
        201,
        headers=auth,
    )
    _, run = call(
        "Create run bound to owned conversation",
        "POST",
        "/api/v1/runs",
        202,
        headers={**auth, "Idempotency-Key": "product-conversation-run"},
        json={
            "asset_id": asset["asset_id"],
            "question": "Mô tả kiến trúc trong ảnh.",
            "conversation_id": conversation["conversation_id"],
        },
    )
    report.wait_for_run(run["run_id"], auth)
    call(
        "Read persisted user and assistant turns",
        "GET",
        conversation_path + "/messages",
        headers=auth,
        check=lambda p: require(
            {i["role"] for i in p["items"]} == {"user", "assistant"},
            "Conversation messages missing",
        ),
    )
    call(
        "Memory is bounded and unverified",
        "GET",
        conversation_path + "/memory",
        headers=auth,
        check=lambda p: require(
            p["unverified_context"] and len(p["items"]) <= 8, "Memory trust/budget wrong"
        ),
    )
    call("Forget prior memory", "DELETE", conversation_path + "/memory", 204, headers=auth)
    call(
        "Forgotten memory does not return",
        "GET",
        conversation_path + "/memory",
        headers=auth,
        check=lambda p: require(p["items"] == [], "Memory was not cleared"),
    )
    call("Delete completed isolated conversation", "DELETE", conversation_path, 204, headers=auth)
    call("Deleted conversation is unavailable", "GET", conversation_path, 404, headers=auth)
    _, recoverable = call(
        "Create isolated recovery fixture run",
        "POST",
        "/api/v1/runs",
        202,
        headers={**auth, "Idempotency-Key": "product-recovery-fixture"},
        json={"asset_id": asset["asset_id"], "question": "Describe visible architecture."},
    )
    report.wait_for_run(recoverable["run_id"], auth)
    run_path = "/api/v1/runs/" + recoverable["run_id"]
    _, recovery = call(
        "Read completed node checkpoint ledger",
        "GET",
        run_path + "/recovery",
        headers=auth,
        check=lambda p: require(
            bool(p["completed_nodes"]) and not p["can_resume"],
            "Completed run checkpoint ledger wrong",
        ),
    )
    call(
        "Completed runs cannot be resumed",
        "POST",
        run_path + "/resume",
        409,
        headers={**auth, "Idempotency-Key": "not-interrupted"},
    )
    # Deliberately inject an interrupted state only in the runner-owned SQLite
    # fixture; this is endpoint acceptance, not a real worker-kill experiment.
    database = Database(database_url)
    try:
        with database.session() as session:
            record = session.scalar(select(Run).where(Run.id == recoverable["run_id"]))
            require(record.execution_status == "succeeded", "Recovery fixture was not terminal")
            record.execution_status, record.error_type, record.result = "failed", "WorkerLost", None
            record.finished_at = time.time()
    finally:
        database.close()
    call(
        "Synthetic interrupted state is resumable",
        "GET",
        run_path + "/recovery",
        headers=auth,
        check=lambda p: require(p["can_resume"], "Interrupted fixture cannot resume"),
    )
    call(
        "Resume interrupted isolated fixture",
        "POST",
        run_path + "/resume",
        202,
        headers={**auth, "Idempotency-Key": "product-resume"},
    )
    report.wait_for_run(recoverable["run_id"], auth)
    call(
        "Replay resume key does not readmit work",
        "POST",
        run_path + "/resume",
        202,
        headers={**auth, "Idempotency-Key": "product-resume"},
        check=lambda p: require(
            p["run_id"] == recoverable["run_id"], "Resume replay created a run"
        ),
    )
    call("Soft-delete isolated terminal run", "DELETE", run_path, 204, headers=auth)
    call("Soft deletion is idempotent", "DELETE", run_path, 204, headers=auth)
    call("Deleted run is hidden from owned reads", "GET", run_path, 404, headers=auth)
    _, current_site = call("Read latest editorial revision", "GET", public)
    call(
        "Archive only synthetic catalog fixture",
        "POST",
        editorial + "/archive",
        headers=auth,
        json={"version": current_site["version"]},
    )
    call("Archived fixture is not public", "GET", public, 404)
    new_password = secrets.token_urlsafe(24)
    call(
        "Change isolated account password",
        "POST",
        "/api/v1/users/me/password",
        204,
        headers=auth,
        json={"current_password": password, "new_password": new_password},
    )
    _, signed = call(
        "Sign in after password rotation",
        "POST",
        "/api/v1/auth/sessions",
        json={"email": email, "password": new_password},
    )
    auth = {"Authorization": "Bearer " + signed["access_token"]}
    call(
        "Revoke only current account session",
        "DELETE",
        "/api/v1/auth/sessions/current",
        204,
        headers=auth,
    )
    call("Revoked account token is rejected", "GET", "/api/v1/users/me", 401, headers=auth)
    return {
        "product_http_cases": True,
        "synthetic_recovery_fixture": True,
        "source_text_fixture_not_historical_gold": True,
    }
