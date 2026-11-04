"""Exercise every OpenAPI operation over real HTTP and write a redacted report.

The runner owns an isolated demo API, database and worker. It never touches the
live API or imports credentials from .env. Run: python -m scripts.api_contract_report
"""

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from PIL import Image
from starlette.routing import compile_path

ROOT = Path(__file__).resolve().parents[1]
SENSITIVE = {"access_token", "authorization", "x-bootstrap-token", "api_key", "password"}


def redact(value):
    if isinstance(value, dict):
        return {
            key: "<REDACTED>" if key.lower() in SENSITIVE else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sse_frames(text):
    frames = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if line.startswith(":") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key] = value.lstrip()
        if "data" in fields:
            fields["data"] = json.loads(fields["data"])
            frames.append(fields)
    return frames


class Reporter:
    def __init__(self, client):
        self.client, self.cases, self.operations = client, [], {}
        self.schema = client.get("/openapi.json").json()
        self.request_count = 1
        for path, methods in self.schema["paths"].items():
            regex, _, _ = compile_path(path)
            for method, operation in methods.items():
                if method in {"get", "post", "put", "delete", "patch"}:
                    self.operations[(method.upper(), path)] = {
                        "regex": regex,
                        "tags": operation.get("tags", []),
                    }

    def request(self, method, path, **kwargs):
        self.request_count += 1
        return self.client.request(method, path, **kwargs)

    def call(self, name, method, path, expected=200, *, check=None, **kwargs):
        method = method.upper()
        operation = next(
            (
                f"{verb} {template}"
                for (verb, template), spec in self.operations.items()
                if verb == method and spec["regex"].fullmatch(path)
            ),
            None,
        )
        started = time.perf_counter()
        response = self.request(method, path, **kwargs)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = response.json()
        elif "text/event-stream" in content_type:
            payload = {"frames": sse_frames(response.text)}
        elif "image/" in content_type:
            with Image.open(BytesIO(response.content)) as image:
                payload = {
                    "bytes": len(response.content),
                    "sha256": hashlib.sha256(response.content).hexdigest(),
                    "format": image.format,
                    "width": image.width,
                    "height": image.height,
                }
        else:
            payload = {"text": response.text}
        failures = []
        if response.status_code != expected:
            failures.append(f"Expected HTTP {expected}, received {response.status_code}")
        if check and not failures:
            try:
                check(payload)
            except AssertionError as exc:
                failures.append(str(exc))
        record = {
            "case_id": f"C{len(self.cases) + 1:02}",
            "name": name,
            "operation": operation,
            "method": method,
            "path": path,
            "request": redact(
                {
                    "headers": kwargs.get("headers", {}),
                    "query": kwargs.get("params", {}),
                    "json": kwargs.get("json"),
                    "files": {
                        key: {
                            "filename": item[0],
                            "bytes": len(item[1]),
                            "media_type": item[2] if len(item) > 2 else None,
                        }
                        for key, item in kwargs.get("files", {}).items()
                    },
                }
            ),
            "expected_status": expected,
            "actual_status": response.status_code,
            "elapsed_ms": elapsed,
            "passed": not failures,
            "failures": failures,
            "response_headers": {
                key: response.headers[key]
                for key in (
                    "content-type",
                    "x-request-id",
                    "location",
                    "content-disposition",
                    "x-accel-buffering",
                    "access-control-allow-origin",
                )
                if key in response.headers
            },
            "response": redact(payload),
        }
        self.cases.append(record)
        if failures:
            raise AssertionError(f"{record['case_id']} {name}: {'; '.join(failures)}")
        return response, payload

    def wait_for_run(self, identifier, auth, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.request("GET", f"/api/v1/runs/{identifier}", headers=auth)
            require(response.status_code == 200, "Status polling failed")
            value = response.json()
            if value["execution_status"] in {"succeeded", "failed", "cancelled"}:
                require(value["execution_status"] == "succeeded", "Demo run did not succeed")
                return
            time.sleep(0.1)
        raise AssertionError("Worker completion timeout")


def exercise(report, start_worker, bootstrap):
    call = report.call
    call(
        "Tiến trình API hoạt động",
        "GET",
        "/health/live",
        check=lambda p: require(p["status"] == "ok", "Unexpected liveness"),
    )
    call(
        "Chưa có worker: readiness trả 503",
        "GET",
        "/health/ready",
        503,
        check=lambda p: require(p["worker"] is False, "Worker should not be ready yet"),
    )
    _, caps = call(
        "Cấu hình demo và giới hạn",
        "GET",
        "/api/v1/capabilities",
        check=lambda p: require(p["model_mode"] == "demo", "Refusing non-demo server"),
    )
    call(
        "Cấp phiên thiếu bootstrap bị từ chối",
        "POST",
        "/api/v1/sessions",
        403,
        json={"label": "blocked"},
    )
    create_headers = {"X-Bootstrap-Token": bootstrap}
    _, session_a = call(
        "Cấp token phiên A",
        "POST",
        "/api/v1/sessions",
        201,
        headers=create_headers,
        json={"label": "Báo cáo kiểm thử A"},
    )
    _, session_b = call(
        "Cấp token phiên B",
        "POST",
        "/api/v1/sessions",
        201,
        headers=create_headers,
        json={"label": "Báo cáo kiểm thử B"},
    )
    auth = {"Authorization": "Bearer " + session_a["access_token"]}
    other = {"Authorization": "Bearer " + session_b["access_token"]}
    call(
        "Đọc phiên đang đăng nhập",
        "GET",
        "/api/v1/sessions/me",
        headers=auth,
        check=lambda p: require(p["session_id"] == session_a["session_id"], "Session mismatch"),
    )
    call("Thiếu token bị từ chối", "GET", "/api/v1/runs", 401)
    call(
        "Token sai bị từ chối",
        "GET",
        "/api/v1/runs",
        401,
        headers={"Authorization": "Bearer invalid-demo-token"},
    )
    call(
        "Sơ đồ và bảy giai đoạn",
        "GET",
        "/api/v1/workflow",
        headers=auth,
        check=lambda p: require(
            len(p["stages"]) == 7 and "graph" in p["diagram"].lower(), "Invalid workflow metadata"
        ),
    )
    call(
        "Danh sách ảnh mẫu",
        "GET",
        "/api/v1/samples",
        check=lambda p: require(
            any(s["sample_id"] == "chua_mot_cot" for s in p["items"]), "Missing sample"
        ),
    )
    data = (ROOT / "samples/chua_mot_cot.jpg").read_bytes()
    _, asset = call(
        "Upload ảnh multipart",
        "POST",
        "/api/v1/assets",
        201,
        headers=auth,
        files={"file": ("chua_mot_cot.jpg", data, "image/jpeg")},
    )
    asset_id = asset["asset_id"]
    call(
        "Danh sách ảnh của phiên",
        "GET",
        "/api/v1/assets",
        headers=auth,
        check=lambda p: require(
            any(a["asset_id"] == asset_id for a in p), "Uploaded asset not listed"
        ),
    )
    call("Metadata ảnh đã chuẩn hóa", "GET", f"/api/v1/assets/{asset_id}", headers=auth)
    call(
        "Tải ảnh PNG",
        "GET",
        f"/api/v1/assets/{asset_id}/content",
        headers=auth,
        check=lambda p: require(
            p["format"] == "PNG" and p["width"] == asset["width"], "Invalid normalized image"
        ),
    )
    call("Phiên B không đọc được ảnh A", "GET", f"/api/v1/assets/{asset_id}", 404, headers=other)
    call("UUID không hợp lệ", "GET", "/api/v1/assets/not-a-uuid", 422, headers=auth)
    call(
        "Từ chối file giả ảnh",
        "POST",
        "/api/v1/assets",
        422,
        headers=auth,
        files={"file": ("bad.png", b"this is not an image", "image/png")},
    )
    oversized = data + b"x" * (caps["max_upload_bytes"] + 1 - len(data))
    call(
        "Từ chối ảnh quá dung lượng",
        "POST",
        "/api/v1/assets",
        413,
        headers=auth,
        files={"file": ("large.jpg", oversized, "image/jpeg")},
    )
    call("Xóa ảnh chưa được sử dụng", "DELETE", f"/api/v1/assets/{asset_id}", 204, headers=auth)
    call("Ảnh đã xóa trả 404", "GET", f"/api/v1/assets/{asset_id}", 404, headers=auth)
    _, asset = call(
        "Tạo asset từ ảnh mẫu", "POST", "/api/v1/samples/chua_mot_cot/assets", 201, headers=auth
    )
    asset_id = asset["asset_id"]
    call("Ảnh mẫu không tồn tại", "POST", "/api/v1/samples/not-found/assets", 404, headers=auth)
    body = {
        "asset_id": asset_id,
        "question": "Những chi tiết kiến trúc nào nhìn thấy rõ trong ảnh?",
        "audience": "tourist",
        "profile": "default",
    }
    idem = {**auth, "Idempotency-Key": "contract-report-main"}
    _, run = call(
        "Tạo run và nhận 202",
        "POST",
        "/api/v1/runs",
        202,
        headers=idem,
        json=body,
        check=lambda p: require(
            p["execution_status"] == "queued", "Run should be queued before worker starts"
        ),
    )
    identifier = run["run_id"]
    base = f"/api/v1/runs/{identifier}"
    call(
        "Gửi trùng key/body trả cùng run",
        "POST",
        "/api/v1/runs",
        202,
        headers=idem,
        json=body,
        check=lambda p: require(
            p["run_id"] == identifier, "Idempotent request created duplicate run"
        ),
    )
    call(
        "Trùng key nhưng khác body trả 409",
        "POST",
        "/api/v1/runs",
        409,
        headers=idem,
        json={**body, "question": "Câu hỏi khác"},
    )
    call(
        "Câu hỏi rỗng trả 422",
        "POST",
        "/api/v1/runs",
        422,
        headers=auth,
        json={**body, "question": "  "},
    )
    call(
        "Profile chưa hỗ trợ trả 422",
        "POST",
        "/api/v1/runs",
        422,
        headers=auth,
        json={**body, "profile": "unknown"},
    )
    call("Không dùng ảnh của phiên khác", "POST", "/api/v1/runs", 404, headers=other, json=body)
    call("Đọc trạng thái queued", "GET", base, headers=auth)
    call("Chưa xong: result trả 409", "GET", base + "/result", 409, headers=auth)
    call(
        "Không retry run còn hoạt động",
        "POST",
        base + "/retry",
        409,
        headers={**auth, "Idempotency-Key": "active-retry"},
    )
    call("Phiên B không đọc được run A", "GET", base, 404, headers=other)
    call("Phiên B không đọc được events A", "GET", base + "/events/history", 404, headers=other)
    call("Phiên B không hủy được run A", "POST", base + "/cancel", 404, headers=other)
    call(
        "Xóa ảnh đang được run sử dụng trả 409",
        "DELETE",
        f"/api/v1/assets/{asset_id}",
        409,
        headers=auth,
    )
    _, cancel_run = call(
        "Tạo run để hủy",
        "POST",
        "/api/v1/runs",
        202,
        headers=auth,
        json={**body, "question": "Run kiểm tra hủy"},
    )
    cancel_base = f"/api/v1/runs/{cancel_run['run_id']}"
    call(
        "Hủy queued có hiệu lực ngay",
        "POST",
        cancel_base + "/cancel",
        headers=auth,
        check=lambda p: require(p["execution_status"] == "cancelled", "Queued cancellation failed"),
    )
    call("Run đã hủy không có answer", "GET", cancel_base + "/result", 409, headers=auth)
    call("Retry bắt buộc Idempotency-Key", "POST", cancel_base + "/retry", 422, headers=auth)
    _, retry_run = call(
        "Retry tạo run mới liên kết parent",
        "POST",
        cancel_base + "/retry",
        202,
        headers={**auth, "Idempotency-Key": "contract-report-retry"},
        check=lambda p: require(p["parent_run_id"] == cancel_run["run_id"], "Missing retry parent"),
    )
    _, spare_run = call(
        "Tạo active run thứ ba",
        "POST",
        "/api/v1/runs",
        202,
        headers=auth,
        json={**body, "question": "Run kiểm tra quota"},
    )
    call(
        "Vượt ba active runs trả 429",
        "POST",
        "/api/v1/runs",
        429,
        headers=auth,
        json={**body, "question": "Run vượt quota"},
    )
    call(
        "Hủy run quota sau kiểm tra",
        "POST",
        f"/api/v1/runs/{spare_run['run_id']}/cancel",
        headers=auth,
    )
    start_worker()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if report.request("GET", "/health/ready").status_code == 200:
            break
        time.sleep(0.1)
    call(
        "Database và worker sẵn sàng",
        "GET",
        "/health/ready",
        check=lambda p: require(p["database"] and p["worker"], "Readiness failed"),
    )
    report.wait_for_run(identifier, auth)
    report.wait_for_run(retry_run["run_id"], auth)
    call(
        "Run đã hoàn tất",
        "GET",
        base,
        headers=auth,
        check=lambda p: require(
            p["execution_status"] == "succeeded" and p["result_status"] == "reviewed",
            "Unexpected completion state",
        ),
    )
    call(
        "Lịch sử có phân trang",
        "GET",
        "/api/v1/runs",
        headers=auth,
        params={"limit": 2, "offset": 0},
        check=lambda p: require(len(p["items"]) == 2 and p["total"] == 4, "Invalid pagination"),
    )
    call(
        "Lọc lịch sử succeeded",
        "GET",
        "/api/v1/runs",
        headers=auth,
        params={"execution_status": "succeeded"},
        check=lambda p: require(p["total"] == 2, "Incorrect success filter"),
    )
    _, history = call(
        "Lịch sử sự kiện JSON",
        "GET",
        base + "/events/history",
        headers=auth,
        check=lambda p: require(
            p["terminal"] and p["items"][-1]["event"] == "run.succeeded", "Missing terminal event"
        ),
    )
    aggregate = [e for e in history["items"] if e["data"].get("node") == "aggregate"][-1]
    require("content" not in aggregate["data"]["payload"], "Default event history leaked draft")
    call(
        "Lịch sử có bản nháp khi opt-in",
        "GET",
        base + "/events/history",
        headers=auth,
        params={"include_draft": True},
        check=lambda p: require(
            any(
                e["data"].get("payload", {}).get("content")
                for e in p["items"]
                if e["data"].get("node") == "aggregate"
            ),
            "Draft missing after opt-in",
        ),
    )
    call(
        "Nhận toàn bộ SSE và terminal event",
        "GET",
        base + "/events",
        headers=auth,
        check=lambda p: require(
            p["frames"][-1]["event"] == "run.succeeded"
            and len(p["frames"]) == len(history["items"]),
            "SSE differs from persisted events",
        ),
    )
    cursor = history["items"][-3]["sequence"]
    call(
        "SSE kết nối lại từ Last-Event-ID",
        "GET",
        base + "/events",
        headers={**auth, "Last-Event-ID": str(cursor)},
        check=lambda p: require(
            [int(e["id"]) for e in p["frames"]]
            == [e["sequence"] for e in history["items"] if e["sequence"] > cursor],
            "SSE replay duplicated/missed events",
        ),
    )
    _, result = call(
        "Kết quả cuối và nguồn",
        "GET",
        base + "/result",
        headers=auth,
        check=lambda p: require(
            p["intermediate"] is None and "DEMO" in p["final_response"] and len(p["sources"]) == 1,
            "Invalid final result",
        ),
    )
    call(
        "Kết quả có nội dung trung gian opt-in",
        "GET",
        base + "/result",
        headers=auth,
        params={"include_intermediate": True},
        check=lambda p: require(bool(p["intermediate"]["draft_response"]), "Missing draft"),
    )
    call(
        "Nguồn có trích dẫn",
        "GET",
        base + "/sources",
        headers=auth,
        check=lambda p: require(
            len(p["items"]) == 1 and p["items"][0]["cited"], "Source registry incorrect"
        ),
    )
    call(
        "Các giai đoạn và bản nháp mặc định ẩn",
        "GET",
        base + "/steps",
        headers=auth,
        check=lambda p: require(
            "content" not in p["items"]["aggregate"]["payload"]
            and p["items"]["visual"]["status"] == "completed",
            "Stage projection incorrect",
        ),
    )
    call(
        "Các giai đoạn bật bản nháp",
        "GET",
        base + "/steps",
        headers=auth,
        params={"include_draft": True},
        check=lambda p: require(
            bool(p["items"]["aggregate"]["payload"]["content"]), "Missing aggregate artifact"
        ),
    )
    call(
        "Metrics demo không tự tạo token usage",
        "GET",
        base + "/metrics",
        headers=auth,
        check=lambda p: require(
            p["usage"]["total_tokens"] is None
            and len(p["calls"]) == 5
            and all(c["actual_provider"] == "demo" for c in p["calls"]),
            "Demo usage/provider incorrect",
        ),
    )
    call(
        "Xuất JSON không kèm draft mặc định",
        "GET",
        base + "/export",
        headers=auth,
        params={"format": "json"},
        check=lambda p: require(p["intermediate"] is None, "Default export includes draft"),
    )
    call(
        "Xuất Markdown",
        "GET",
        base + "/export",
        headers=auth,
        params={"format": "markdown"},
        check=lambda p: require(
            "Mode: demo" in p["text"] and "Báo cáo khám phá di sản" in p["text"],
            "Invalid Markdown export",
        ),
    )
    call(
        "Đánh dấu run",
        "PUT",
        base + "/bookmark",
        headers=auth,
        json={"saved": True},
        check=lambda p: require(p["bookmarked"], "Bookmark was not saved"),
    )
    call(
        "Lọc các run đã lưu",
        "GET",
        "/api/v1/runs",
        headers=auth,
        params={"saved_only": True},
        check=lambda p: require(
            p["total"] == 1 and p["items"][0]["run_id"] == identifier, "Saved filter incorrect"
        ),
    )
    feedback = {"rating": "helpful", "note": "Kiểm thử API: nguồn và tiến trình dễ quan sát."}
    call(
        "Ghi phản hồi bằng POST",
        "POST",
        base + "/feedback",
        headers=auth,
        json=feedback,
        check=lambda p: require(p == feedback, "Feedback differs"),
    )
    call(
        "Đọc phản hồi đã lưu",
        "GET",
        base + "/feedback",
        headers=auth,
        check=lambda p: require(p == feedback, "Feedback not persisted"),
    )
    feedback = {"rating": "needs_review", "note": "Cập nhật phản hồi qua PUT."}
    call(
        "Cập nhật phản hồi bằng PUT",
        "PUT",
        base + "/feedback",
        headers=auth,
        json=feedback,
        check=lambda p: require(p == feedback, "Feedback update failed"),
    )
    call(
        "Xác nhận cập nhật phản hồi",
        "GET",
        base + "/feedback",
        headers=auth,
        check=lambda p: require(p == feedback, "Feedback update was not persisted"),
    )
    call("Thu hồi token phiên B", "DELETE", "/api/v1/sessions/me", 204, headers=other)
    call("Token đã thu hồi trả 401", "GET", "/api/v1/sessions/me", 401, headers=other)
    call("Thu hồi token phiên A", "DELETE", "/api/v1/sessions/me", 204, headers=auth)
    return {
        "primary_run_id": identifier,
        "asset_id": asset_id,
        "event_count": len(history["items"]),
        "source_count": len(result["sources"]),
        "model_calls": 5,
        "paid_model_calls": 0,
    }


def summarize_response(record):
    payload = record["response"]
    if isinstance(payload, dict) and "error" in payload:
        return "error.code=" + payload["error"]["code"]
    if not payload:
        return "Không có response body"
    if record["actual_status"] == 204:
        return "Không có response body"
    if isinstance(payload, list):
        return f"{len(payload)} bản ghi"
    if "frames" in payload:
        return f"{len(payload['frames'])} SSE events"
    if "access_token" in payload:
        return "Đã cấp access_token; token được che trong báo cáo"
    if "execution_status" in payload:
        return "execution_status=" + payload["execution_status"]
    if "final_response" in payload:
        return f"status={payload['status']}; sources={len(payload['sources'])}"
    if "format" in payload:
        return (
            f"{payload['format']}, {payload['width']}×{payload['height']}, {payload['bytes']} bytes"
        )
    if "rating" in payload:
        return "rating=" + payload["rating"]
    if "items" in payload:
        return f"items={len(payload['items'])}"
    if "text" in payload:
        return "Đã nhận báo cáo Markdown"
    if "calls" in payload:
        return f"{len(payload['calls'])} model calls; total_tokens=null (demo)"
    return (
        "; ".join(
            f"{key}={payload[key]}"
            for key in ("status", "model_mode", "version", "session_id")
            if key in payload
        )
        or "JSON hợp lệ"
    )


def write_report(report, summary, json_path, markdown_path, base_url):
    covered = {c["operation"] for c in report.cases if c["operation"] and c["passed"]}
    expected = {f"{method} {path}" for method, path in report.operations}
    missing = sorted(expected - covered)
    failures = [c for c in report.cases if not c["passed"]]
    bundle = {
        "tested_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
        "base_url": base_url,
        "model_mode": "demo",
        "database": "isolated SQLite",
        "worker": "separate process",
        "openapi_operations": len(expected),
        "covered_operations": len(covered),
        "missing_operations": missing,
        "case_count": len(report.cases),
        "passed": len(report.cases) - len(failures),
        "failed": len(failures),
        "http_requests": report.request_count,
        "summary": summary,
        "cases": report.cases,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Kết quả kiểm thử từng API",
        "",
        f"Thời điểm: {bundle['tested_at']} (Asia/Ho_Chi_Minh).",
        f"Base URL: `{base_url}`. Chạy HTTP thật với API và worker riêng, SQLite riêng, **demo mode**.",
        "Không gọi Gemini/GPU thật; báo cáo này kiểm tra hợp đồng API và workflow, không đo chất lượng AI.",
        "",
        f"- OpenAPI: **{len(covered)}/{len(expected)} operations** đã được gọi và kiểm tra.",
        f"- Kịch bản: **{bundle['passed']}/{len(report.cases)} đạt**, {len(failures)} lỗi.",
        f"- Run chính: `{summary.get('primary_run_id', 'chưa hoàn tất')}`.",
        f"- Run chính phát {summary.get('event_count', '?')} events, trả {summary.get('source_count', '?')} nguồn minh họa; model calls trả phí: **0**.",
        "- Token và bootstrap credential đã được che; thời gian dưới đây chỉ là một lượt local, không phải benchmark.",
        "",
        "## Tổng hợp theo từng API",
        "",
        "| # | Method | Endpoint | HTTP thực nhận | Số case | Kết quả |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for index, (method, path) in enumerate(report.operations, 1):
        key = f"{method} {path}"
        cases = [c for c in report.cases if c["operation"] == key]
        statuses = ", ".join(map(str, sorted({c["actual_status"] for c in cases}))) or "—"
        passed = bool(cases) and all(c["passed"] for c in cases)
        lines.append(
            f"| {index} | {method} | `{path}` | {statuses} | {len(cases)} | {'Đạt' if passed else 'Chưa đạt'} |"
        )
    lines.extend(
        [
            "",
            "## Chi tiết các tình huống",
            "",
            "HTTP 4xx/503 trong case âm là kết quả đúng khi trùng với kỳ vọng.",
            "",
            "| Case | Tình huống | Kỳ vọng | Thực nhận | ms | Kết quả trả về | Kết luận |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in report.cases:
        lines.append(
            f"| {record['case_id']} | {record['name']} | {record['expected_status']} | {record['actual_status']} | {record['elapsed_ms']} | {summarize_response(record).replace('|', '/')} | {'Đạt' if record['passed'] else 'Lỗi'} |"
        )
    lines.extend(
        [
            "",
            "## Xem request/response đầy đủ",
            "",
            "Dữ liệu phản hồi thật, request, header đã che token và assertion của từng case nằm ở",
            "[results.json](../reports/api-contract/results.json). File này được tạo local, không commit cùng source.",
            "Ảnh tải về được ghi nhận bằng format, kích thước, số byte và SHA-256; SSE được parse thành các frame.",
            "",
            "## Chạy lại",
            "",
            "```powershell",
            "uv run --locked python -m scripts.api_contract_report",
            "```",
            "",
            "Lệnh tạo server demo tạm trên port 18512, tạo worker riêng và tự dừng cả hai khi xong.",
            "Không thay đổi `.env`, không gửi request vào server live port 8000. Có thể đổi `--port`.",
            "Hướng dẫn thao tác thủ công từng API: [api-swagger-walkthrough.md](api-swagger-walkthrough.md).",
            "",
        ]
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18512)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/api-contract/results.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "docs/api-test-results.md")
    args = parser.parse_args()
    # Do not stop/reuse a server we did not launch.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    work = ROOT / ".api-demo" / ("contract-" + uuid4().hex)
    work.mkdir(parents=True)
    bootstrap = secrets.token_urlsafe(32)
    env = {
        **os.environ,
        "PYTHON_DOTENV_DISABLED": "1",
        "LANGSMITH_TRACING": "false",
        "API_ENV": "development",
        "API_MODEL_MODE": "demo",
        "API_EMBEDDED_WORKER": "false",
        "DATABASE_URL": "sqlite:///" + (work / "api.sqlite").as_posix(),
        "API_DATA_DIR": str(work / "assets"),
        "API_BOOTSTRAP_TOKEN": bootstrap,
        "API_MAX_ACTIVE_PER_OWNER": "3",
        "API_MAX_PENDING_RUNS": "100",
        "API_MAX_RUNS_PER_DAY": "100",
        "API_MAX_UPLOAD_BYTES": "10000000",
    }
    children = []
    report, summary = None, {}
    base_url = f"http://127.0.0.1:{args.port}"

    def launch(module, *arguments):
        child = subprocess.Popen(
            [sys.executable, "-m", module, *arguments],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        children.append(child)
        return child

    try:
        api = launch("scripts.serve_api", "--demo", "--port", str(args.port))
        with httpx.Client(base_url=base_url, timeout=20) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                require(api.poll() is None, "Managed demo API exited before startup")
                try:
                    if client.get("/health/live").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Managed demo API startup timed out")
            report = Reporter(client)
            summary = exercise(report, lambda: launch("api.worker"), bootstrap)
    except Exception as exc:
        summary["runner_error_type"] = type(exc).__name__
        # Assertion text is generated by this runner, never an HTTP exception body.
        if isinstance(exc, AssertionError):
            summary["runner_error"] = str(exc)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
    if report is None:
        print({"report": "failed", **summary})
        return 1
    bundle = write_report(report, summary, args.output, args.markdown, base_url)
    print(
        {
            key: bundle[key]
            for key in (
                "model_mode",
                "openapi_operations",
                "covered_operations",
                "case_count",
                "passed",
                "failed",
            )
        }
    )
    if summary.get("runner_error_type"):
        print(summary)
    return (
        0
        if not bundle["missing_operations"]
        and not bundle["failed"]
        and "runner_error_type" not in summary
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
