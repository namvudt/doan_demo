"""Prepare draft cases, run isolated predictions, and score only human-reviewed evidence."""

import argparse
import hashlib
import json
from pathlib import Path

from core.config import load_config
from core.evaluation import digest, score, validate_manifest

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def prepare(pilot):
    return [
        {
            "case_id": f"{image['family']}_{question['id']}",
            "image_path": image["path"],
            "image_family": image["family"],
            "entity_group": image["entity_group"],
            "question": question["text"],
            "slots": [
                {"slot_id": question["id"], "question": question["text"], "kind": question["kind"]}
            ],
        }
        for image in pilot["images"]
        for question in pilot["questions"]
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("prepare")
    setup.add_argument("--pilot", type=Path, default=ROOT / "config/evaluation/hanoi-pilot.json")
    setup.add_argument("--output", type=Path, default=ROOT / "data/evaluation/hanoi-draft.json")
    run = sub.add_parser("run")
    run.add_argument("manifest", type=Path)
    run.add_argument("--config", type=Path, default=ROOT / "config/hanoi-evidence.yaml")
    mode = run.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument(
        "--live", action="store_true", help="Calls configured model and sources; may incur charges"
    )
    run.add_argument(
        "--allow-draft",
        action="store_true",
        help="Development only, cannot produce quality metrics",
    )
    run.add_argument("--limit", type=int)
    run.add_argument("--output", required=True, type=Path)
    scoring = sub.add_parser("score")
    scoring.add_argument("manifest", type=Path)
    scoring.add_argument("predictions", type=Path)
    scoring.add_argument("judgments", type=Path)
    scoring.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        data = [
            c.model_dump(mode="json")
            for c in validate_manifest(prepare(read(args.pilot)), allow_draft=True)
        ]
    elif args.command == "score":
        data = score(read(args.manifest), read(args.predictions), read(args.judgments))
    else:
        cases = validate_manifest(read(args.manifest), allow_draft=args.allow_draft)
        if args.limit is not None and args.limit <= 0:
            parser.error("--limit must be positive")
        from workflow.service import RunService

        if args.demo:
            from api.demo import DemoManager, DemoSearch

            manager = DemoManager(load_config(args.config))
            service = RunService(manager, search_engine_factory=DemoSearch)
        else:
            from dotenv import load_dotenv

            from core.gateway import LLMManager

            load_dotenv()
            manager = LLMManager(config=load_config(args.config))
            service = RunService(manager, benchmark=True)
        data = []
        try:
            for case in cases[: args.limit]:
                path = Path(case.image_path)
                content = (path if path.is_absolute() else ROOT / path).read_bytes()
                result = service.run(content, case.question)
                data.append(
                    {
                        "case_id": case.case_id,
                        "case_hash": digest(case.model_dump(mode="json")),
                        "image_hash": hashlib.sha256(content).hexdigest(),
                        "model_mode": "demo" if args.demo else "live",
                        "result": result.model_dump(mode="json"),
                    }
                )
                # Save completed cases even if a later case/provider fails.
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        finally:
            manager.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Saved {args.output}; {len(data)} entries. Draft/demo outputs are not gold accuracy measurements."
    )


if __name__ == "__main__":
    main()
