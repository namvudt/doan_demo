"""Convenient launcher: python -m scripts.serve_api [--demo] [--port 8000]."""

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Start Heritage VQA API and Swagger UI")
    parser.add_argument(
        "--demo", action="store_true", help="Offline graph; no billable model calls"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--profile", choices=["default", "hanoi-evidence"])
    args = parser.parse_args()
    if args.demo:
        if os.environ.get("DATABASE_URL", "sqlite:").startswith(("postgres", "mysql")):
            parser.error("Demo requires an isolated SQLite DATABASE_URL; use a separate terminal")
        os.environ["API_MODEL_MODE"] = "demo"
        os.environ["PYTHON_DOTENV_DISABLED"] = "1"
        os.environ["API_ENV"] = "development"
        os.environ["LANGSMITH_TRACING"] = "false"
        root = Path(__file__).resolve().parents[1] / ".api-demo" / "interactive"
        os.environ.setdefault("DATABASE_URL", "sqlite:///" + (root / "api.sqlite").as_posix())
        os.environ.setdefault("API_DATA_DIR", str(root / "media"))
    if args.profile:
        os.environ["HERITAGE_CONFIG"] = str(
            Path(__file__).resolve().parents[1] / "config" / (args.profile + ".yaml")
        )
    import uvicorn

    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
