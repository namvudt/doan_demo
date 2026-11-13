import json
import os
import socket
import threading

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["LANGSMITH_TRACING"] = "false"

import pytest
from PIL import Image

from core.config import ROLES, AppConfig
from core.images import image_bytes
from core.search import HeritageSearchEngine


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original_connect = socket.socket.connect

    def blocked(sock, address):
        # Windows asyncio implements socketpair using a loopback connection.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        raise AssertionError("Network is disabled in offline tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    for name in [
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "HERITAGE_CONFIG",
        "GEMINI_MODEL",
        "OPENAI_MODEL",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGSMITH_ENDPOINT",
        "LANGSMITH_WORKSPACE_ID",
        "LANGSMITH_CAPTURE_CONTENT",
        "HERITAGE_API_URL",
        "HERITAGE_API_TOKEN",
        *[
            f"{role.upper()}_{suffix}"
            for role in ROLES
            for suffix in ("API_KEY", "MODEL", "PROVIDER")
        ],
    ]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def photo():
    return image_bytes(Image.new("RGB", (40, 30), "green"))


@pytest.fixture
def source():
    return {
        "source_id": "wiki_a",
        "title": "Test monument",
        "url": "https://vi.wikipedia.org/wiki/Test",
        "type": "wiki",
        "snippet": "Test documented historical fact.",
        "retrieved_at": "2026-10-29T00:00:00+00:00",
        "revision_id": "123",
    }


@pytest.fixture
def fake_search(monkeypatch, source):
    payload = {
        "status": "success",
        "error": None,
        "sources": [source],
        "navigation_links": [],
        "context_text": "[wiki_a] Test fact",
    }
    monkeypatch.setattr(HeritageSearchEngine, "search_heritage", lambda *a, **k: payload)
    return payload


def valid_review():
    return {
        "criteria_evaluation": {
            name: {"passed": True, "score": 8, "critique": "mock"}
            for name in ("visual_fidelity", "relevance", "cultural_tone")
        },
        "overall_status": "APPROVED",
        "hallucination_detected": False,
        "hallucination_notes": "mock",
        "final_response": "Answer [wiki_a]",
        "cited_source_ids": ["wiki_a"],
    }


class FakeLLM:
    def preflight(self, roles=None, *, force=False):
        from core.preflight import MANDATORY_ROLES

        return {
            "ready": True,
            "roles": [
                {"role": r, "provider": "mock", "model": "mock", "ready": True, "cached": False}
                for r in (roles or MANDATORY_ROLES)
            ],
            "scope": "mock",
            "generation_verified": False,
        }

    def __init__(self, behavior=None, config=None, history=None, lock=None):
        self.config = config or AppConfig()
        self.behavior = behavior
        self.calls = []
        self.history = history if history is not None else []
        self.lock = lock or threading.Lock()

    def for_run(self, benchmark=False):
        config = (
            self.config.model_copy(update={"fallback_providers": []}) if benchmark else self.config
        )
        return FakeLLM(self.behavior, config, self.history, self.lock)

    def close(self):
        pass

    def get_status(self):
        return {"ready": True, "roles": {}, "description": "mock"}

    def call_llm(self, **kwargs):
        role = kwargs.get("agent_role", "general")
        with self.lock:
            record = {
                "attempt": len(self.calls) + 1,
                "actual_provider": "mock",
                "model_used": "mock",
                "agent_role": role,
                "usage": None,
                "status": "success",
            }
            self.calls.append(record)
            self.history.append(kwargs)
        answer = self.behavior(role, kwargs) if self.behavior else None
        if answer is None:
            if role == "coordinator":
                answer = json.dumps(
                    {
                        "selected_agents": ["visual_agent", "knowledge_agent"],
                        "identified_monument": "Test monument",
                    }
                )
            elif role == "judge":
                answer = json.dumps(valid_review())
            else:
                answer = f"mock {role} findings"
        return answer, record
