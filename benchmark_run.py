"""CLI adapter for the same workflow used by the Streamlit app."""

import argparse
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

from core.gateway import LLMManager
from core.runtime_logging import configure_local_logging, log_event
from workflow.comparison import compare
from workflow.service import RunService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", default="samples/chua_mot_cot.jpg")
    parser.add_argument(
        "query", nargs="?", default="Identify this heritage site and explain its history."
    )
    parser.add_argument(
        "--compare", action="store_true", help="Descriptive comparison; no accuracy scores"
    )
    parser.add_argument("--audience", choices=["tourist", "student"], default="tourist")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    load_dotenv()
    configure_local_logging(role="cli")
    manager = None
    try:
        manager = LLMManager()
        data = Path(args.image).read_bytes()
        if args.compare:
            result = compare(data, args.query, manager, args.audience)
        else:
            result = (
                RunService(manager).run(data, args.query, args.audience).model_dump(mode="json")
            )
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload)
        if result.get("status") in {"failed", "unverified"}:
            return 1
        return 0
    except Exception as exc:
        log_event("cli.run_failed", level=logging.ERROR, error=exc)
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 1
    finally:
        if manager:
            manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
