"""Optional Streamlit HTTP adapter, also illustrating the frontend API contract."""

import time
from uuid import uuid4

import httpx

from core.config import AppConfig
from core.images import fingerprint
from core.schemas import RunEvent, RunResult, StageEvent


class RemoteManager:
    def __init__(self, base_url, *, token=None, bootstrap_token=None, transport=None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.bootstrap_token = bootstrap_token
        self.transport = transport
        caps = self.request("GET", "/api/v1/capabilities", authenticated=False)
        self.capabilities = caps
        if not self.token:
            headers = {"X-Bootstrap-Token": bootstrap_token} if bootstrap_token else {}
            created = self.request(
                "POST",
                "/api/v1/sessions",
                authenticated=False,
                headers=headers,
                json={"label": "Streamlit frontend"},
            )
            self.token = created["access_token"]
        self.request("GET", "/api/v1/sessions/me")
        self.config = AppConfig(
            max_image_bytes=caps["max_upload_bytes"],
            max_image_pixels=caps["max_image_pixels"],
            workflow_version=caps["profiles"][0]["workflow_version"],
        )

    def request(self, method, path, *, authenticated=True, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if authenticated:
            headers["Authorization"] = "Bearer " + self.token
        with httpx.Client(base_url=self.base_url, timeout=30, transport=self.transport) as client:
            response = client.request(method, path, headers=headers, **kwargs)
            if not response.is_success:
                # Do not expose request/response bodies or credentials in UI errors.
                raise RuntimeError(f"API returned HTTP {response.status_code}")
            return response.json()

    def get_status(self):
        return {
            "ready": self.capabilities["model_configured"],
            "missing_roles": self.capabilities["missing_roles"],
            "roles": {},
            "description": f"Backend API · {self.capabilities['model_mode']} · {self.base_url}",
        }

    def close(self):
        pass  # HTTP clients are scoped to each request.

    def remote_stream(self, image_data, query, audience):
        asset = self.request(
            "POST", "/api/v1/assets", files={"file": ("photo.png", image_data, "image/png")}
        )
        run = self.request(
            "POST",
            "/api/v1/runs",
            headers={"Idempotency-Key": str(uuid4())},
            json={"asset_id": asset["asset_id"], "question": query, "audience": audience},
        )
        identifier = run["run_id"]
        base = f"/api/v1/runs/{identifier}"
        cursor, events, terminal = 0, [], False
        while not terminal:
            page = self.request(
                "GET", base + "/events/history", params={"after": cursor, "include_draft": True}
            )
            for item in page["items"]:
                if item["event"].startswith("stage."):
                    event = RunEvent.model_validate(item["data"])
                    events.append(
                        StageEvent.model_validate(
                            event.model_dump(exclude={"kind", "run_id", "result"})
                        )
                    )
                    yield event
                if item["event"] in {"run.succeeded", "run.failed", "run.cancelled"}:
                    terminal = True
            cursor = page["next_after"]
            if not terminal:
                time.sleep(0.3)
        payload = self.request("GET", base + "/result", params={"include_intermediate": True})
        metrics = self.request("GET", base + "/metrics")
        stages = payload["intermediate"]["stages"]
        sources = [
            {k: v for k, v in s.items() if k not in {"number", "cited"}} for s in payload["sources"]
        ]
        experts = {}
        for name in ("visual", "knowledge", "generation"):
            artifact = stages.get(name, {}).get("payload", {})
            if artifact.get("content"):
                experts[name] = {"text": artifact["content"], "meta": {}}
                if name == "knowledge":
                    experts[name]["meta"] = {
                        "live_search_sources": sources,
                        "search_status": artifact.get("search_status"),
                        "navigation_links": artifact.get("navigation_links", []),
                    }
        plan = stages.get("coordinate", {}).get("payload", {}).get("plan", payload["plan"])
        snapshot = {
            "workflow_version": metrics["workflow_version"],
            "config_hash": metrics["config_hash"],
        }
        report = {
            **payload["review"],
            "final_response": payload["final_response"],
            "sources": [
                source
                for source, full in zip(sources, payload["sources"], strict=True)
                if full["cited"]
            ],
        }
        result = RunResult(
            run_id=identifier,
            fingerprint=fingerprint(image_data, query, audience, metrics["config_hash"]),
            query=query,
            audience=audience,
            status=payload["status"],
            final_response=payload["final_response"],
            draft_response=payload["intermediate"]["draft_response"],
            plan=plan,
            expert_results=experts,
            judge_report=report,
            errors=payload["errors"],
            events=events,
            calls=metrics["calls"],
            config_snapshot=snapshot,
            duration=payload["duration"],
            node_metadata={
                name: {"status": stage["status"], "duration": stage["duration"]}
                for name, stage in stages.items()
            },
        )
        yield RunEvent(kind="completed", node="finish", run_id=identifier, result=result)
