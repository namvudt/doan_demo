"""Explicit offline provider for testing the real graph and HTTP contracts."""

import json
import threading


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
    def __init__(self, config):
        self.config, self.calls = config, []
        self.lock = threading.Lock()
        self.cancel_check = None

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
            }
            self.calls.append(record)
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
