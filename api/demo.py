"""Explicit offline provider for testing the real graph and HTTP contracts."""

import json
import threading
import time

from core.runtime_logging import log_event


class DemoSearch:
    def search_heritage(self, **kwargs):
        return {
            "status": "success",
            "error": None,
            "navigation_links": [],
            "context_text": "[wiki_demo] Dữ liệu mô phỏng để thử API, không phải tư liệu lịch sử.",
            "sources": [
                {
                    "source_id": "wiki_demo",
                    "title": "Nguồn minh họa API (demo)",
                    "url": "https://example.org/heritage-demo",
                    "type": "web",
                    "snippet": "Dữ liệu mô phỏng để thử API, không phải tư liệu lịch sử.",
                    "revision_id": "demo-v1",
                    "retrieved_at": "2026-11-04T00:00:00+00:00",
                }
            ],
        }


class DemoManager:
    def preflight(self, roles=None, *, force=False):
        from core.preflight import MANDATORY_ROLES

        return {
            "ready": True,
            "roles": [
                {
                    "role": r,
                    "provider": "demo",
                    "model": "offline-demo-v1",
                    "ready": True,
                    "cached": False,
                    "error_code": None,
                    "retryable": False,
                }
                for r in (roles or MANDATORY_ROLES)
            ],
            "scope": "offline_demo",
            "generation_verified": False,
        }

    def __init__(self, config):
        self.config, self.calls = config, []
        self.lock = threading.Lock()
        self.cancel_check = None
        self.attempt_observer = None

    def for_run(self, benchmark=False):
        return DemoManager(self.config)

    def get_status(self):
        return {"ready": True, "missing_roles": []}

    def close(self):
        pass

    def call_llm(self, *, agent_role=None, **kwargs):
        if self.cancel_check:
            self.cancel_check()
        with self.lock:
            record = {
                "attempt": len(self.calls) + 1,
                "agent_role": agent_role,
                "actual_provider": "demo",
                "model_used": "offline-demo-v1",
                "usage": None,
                "status": "success",
                "duration": 0.0,
                "started_at": time.time(),
                "finished_at": time.time(),
            }
            self.calls.append(record)
        if self.attempt_observer:
            self.attempt_observer({**record, "status": "running", "finished_at": None})
            self.attempt_observer(record)
        log_event("model.success", **{k: v for k, v in record.items() if k != "usage"})
        if self.config.accuracy.enabled:
            result = evidence_demo_response(kwargs.get("response_schema"), kwargs.get("prompt", ""))
            if result is not None:
                return json.dumps(result, ensure_ascii=False), record
        if agent_role == "coordinator":
            text = json.dumps(
                {
                    "selected_agents": ["visual_agent", "knowledge_agent"],
                    "identified_monument": "Địa điểm minh họa (chưa nhận diện thật)",
                    "query_intent": "Kiểm tra luồng API bằng dữ liệu mô phỏng",
                }
            )
        elif agent_role == "judge":
            text = json.dumps(
                {
                    "criteria_evaluation": {
                        name: {
                            "passed": True,
                            "score": 5,
                            "critique": "Kết quả mô phỏng, không đánh giá chất lượng thật.",
                        }
                        for name in ("visual_fidelity", "relevance", "cultural_tone")
                    },
                    "overall_status": "APPROVED",
                    "hallucination_detected": False,
                    "hallucination_notes": "DEMO: Không gọi model thật.",
                    "final_response": "**DEMO** — Luồng API hoạt động. Nội dung này chỉ để kiểm thử, không cung cấp thông tin lịch sử. [wiki_demo]",
                    "cited_source_ids": ["wiki_demo"],
                }
            )
        else:
            text = f"DEMO — Báo cáo {agent_role} mô phỏng để quan sát kết quả trung gian."
        return text, record


def evidence_demo_response(schema, prompt):
    """Synthetic fixtures, explicitly labelled; never historical ground truth."""
    name = getattr(schema, "__name__", "")
    if name == "ExecutionPlan":
        return {
            "selected_agents": ["visual_agent", "knowledge_agent"],
            "identified_monument": "DEMO",
            "candidates": [{"name": "DEMO", "reason": "Dữ liệu mô phỏng"}],
            "requested_slots": [
                {"slot_id": "answer", "question": "Câu hỏi minh họa", "evidence_type": "mixed"}
            ],
            "regions": [],
        }
    if name == "VisualFindings":
        return {
            "observations": [
                {"text": "DEMO: ảnh dùng kiểm tra luồng, chưa nhận diện thực tế.", "box": None}
            ],
            "candidates": ["DEMO"],
            "readability": "adequate",
        }
    if name == "OCROutput":
        return {"readable": False, "lines": []}
    if name == "EvidenceReview":
        data = json.loads(prompt)
        source = next((e for e in data["evidence"] if e["kind"] == "source"), None)
        evidence = source or next(iter(data["evidence"]), None)
        if not evidence:
            return {"claims": []}
        return {
            "claims": [
                {
                    "slot_id": data["requested_slots"][0]["slot_id"],
                    "text": "DEMO — " + evidence["text"],
                    "kind": "historical" if source else "visual",
                    "verdict": "supported",
                    "evidence_ids": [evidence["evidence_id"]],
                    "quotations": [
                        {"evidence_id": evidence["evidence_id"], "quote": evidence["text"]}
                    ]
                    if source
                    else [],
                    "explanation": "Kết quả mô phỏng chỉ dùng test, không đánh giá độ đúng lịch sử.",
                }
            ]
        }
    return None
