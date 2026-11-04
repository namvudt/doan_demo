"""Convenient launcher: python -m scripts.serve_api [--demo] [--port 8000]."""

import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="Start Heritage VQA API and Swagger UI")
    parser.add_argument(
        "--demo", action="store_true", help="Offline graph; no billable model calls"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    if args.demo:
        os.environ["API_MODEL_MODE"] = "demo"
    import uvicorn

    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
