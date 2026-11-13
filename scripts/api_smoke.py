"""End-to-end HTTP smoke; refuses live mode unless --allow-live is explicit."""

import argparse
import time

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    from api.settings import Settings

    settings = Settings.from_env()
    with httpx.Client(base_url=args.url, timeout=15) as client:
        caps = client.get("/api/v1/capabilities")
        caps.raise_for_status()
        if caps.json()["model_mode"] != "demo" and not args.allow_live:
            print("Server is live. Use --allow-live explicitly to permit a billable workflow.")
            return 2
        headers = {}
        if key := settings.bootstrap_token.get_secret_value():
            headers["X-Bootstrap-Token"] = key
        created = client.post("/api/v1/sessions", headers=headers, json={"label": "HTTP smoke"})
        created.raise_for_status()
        auth = {"Authorization": "Bearer " + created.json()["access_token"]}
        try:
            asset = client.post("/api/v1/samples/chua_mot_cot/assets", headers=auth)
            asset.raise_for_status()
            queued = client.post(
                "/api/v1/runs",
                headers={**auth, "Idempotency-Key": "smoke-v1"},
                json={
                    "asset_id": asset.json()["asset_id"],
                    "question": "Những chi tiết kiến trúc nào nhìn thấy rõ?",
                },
            )
            queued.raise_for_status()
            run_id = queued.json()["run_id"]
            base = f"/api/v1/runs/{run_id}"
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                response = client.get(base, headers=auth)
                response.raise_for_status()
                if response.json()["execution_status"] in {"succeeded", "failed", "cancelled"}:
                    break
                time.sleep(0.2)
            else:
                print({"smoke": "failed", "reason": "worker_timeout", "run_id": run_id})
                return 1
            result = client.get(base + "/result?include_intermediate=true", headers=auth)
            result.raise_for_status()
            history = client.get(base + "/events/history", headers=auth)
            history.raise_for_status()
            feedback = client.post(
                base + "/feedback", headers=auth, json={"rating": "helpful", "note": "HTTP smoke"}
            )
            feedback.raise_for_status()
            with client.stream("GET", base + "/events", headers=auth) as stream:
                stream.raise_for_status()
                has_terminal = any("event: run.succeeded" in line for line in stream.iter_lines())
            assert has_terminal, "SSE did not include terminal event"
            print(
                {
                    "smoke": "passed",
                    "model_mode": caps.json()["model_mode"],
                    "run_id": run_id,
                    "event_count": len(history.json()["items"]),
                    "sources": len(result.json()["sources"]),
                    "swagger": args.url.rstrip("/") + "/docs",
                }
            )
            return 0
        finally:
            client.delete("/api/v1/sessions/me", headers=auth)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print({"smoke": "failed", "error_type": type(exc).__name__})
        raise SystemExit(1) from None
