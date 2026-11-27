"""Prepare draft cases, run isolated predictions, and score only human-reviewed evidence."""

import argparse
import hashlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from core.config import load_config
from core.evaluation import digest, score, validate_manifest
from core.evaluation_runtime import EvaluationGate, EvaluationPolicy, PacedLLMManager
from core.model_errors import failure_info

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


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def output_lock(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_name(output.name + ".lock")
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def run_predictions(
    cases,
    service,
    *,
    output,
    policy,
    gate,
    model_mode,
    resume=False,
    sleep=time.sleep,
    wall=time.time,
    pause_check=None,
):
    """Checkpoint each attempt; resuming never silently buys the same case again."""
    config_hash = digest(service.config.snapshot())
    progress = output.with_suffix(".run.json")
    with output_lock(output):
        if output.exists() and not resume:
            raise ValueError("Output exists; use --resume or choose a new output")
        if resume and not output.exists():
            raise ValueError("Resume requires an existing predictions file")
        if resume and not progress.exists():
            raise ValueError("Resume requires its run checkpoint; provider budget is unknown")
        records = read(output) if resume else []
        previous = read(progress) if resume and progress.exists() else {}
        if previous.get("active_case_id"):
            raise ValueError("Interrupted case requires review; refusing automatic paid replay")
        if previous.get("retry_not_before", 0) and previous["retry_not_before"] > wall():
            raise ValueError("Quota cooldown is still active; no provider request was sent")
        by_id = {case.case_id: case for case in cases}
        seen = set()
        for record in records:
            case = by_id.get(record["case_id"])
            if not case or case.case_id in seen:
                raise ValueError("Resume cases differ or contain duplicate predictions")
            seen.add(case.case_id)
            if (
                record.get("case_hash") != digest(case.model_dump(mode="json"))
                or record.get("model_mode") != model_mode
                or record.get("workflow_config_hash") != config_hash
            ):
                raise ValueError("Resume manifest, model mode or workflow configuration changed")
        # Validate all local inputs before any paid call, including skipped records.
        images = {}
        for case in cases:
            path = Path(case.image_path)
            content = (path if path.is_absolute() else ROOT / path).read_bytes()
            from core.images import validate_image

            validate_image(content, service.config)
            image_hash = hashlib.sha256(content).hexdigest()
            images[case.case_id] = content, image_hash
        if any(record["image_hash"] != images[record["case_id"]][1] for record in records):
            raise ValueError("Resume image content changed")
        if resume:
            gate.provider_calls = int(previous.get("provider_calls", 0))
            gate.request_start_times = list(previous.get("request_start_times", []))
            gate.credential_slot = previous.get("credential_slot", "primary")
            gate.provider_events = list(previous.get("provider_events", []))
            gate.failure_streak = int(previous.get("failure_streak", 0))
        pending = [case for case in cases if case.case_id not in seen][: policy.max_cases]
        save(output, records)
        active_case_id = None

        def checkpoint(status):
            save(
                progress,
                {
                    "evaluation_status": "predictions_only_not_human_scored",
                    "status": status,
                    "model_mode": model_mode,
                    "workflow_config_hash": config_hash,
                    "policy": policy.model_dump(),
                    "completed_case_ids": [record["case_id"] for record in records],
                    "active_case_id": active_case_id,
                    "remaining_case_ids": [
                        case.case_id for case in cases if case.case_id not in seen
                    ],
                    "updated_at": wall(),
                    **gate.snapshot(),
                },
            )

        checkpoint("running")
        gate.on_change = lambda: checkpoint("running")
        if resume and pending:
            # Also space the first case of a resumed process.
            sleep(policy.case_spacing_seconds)
        for index, case in enumerate(pending):
            if pause_check and pause_check():
                gate.stop_reason = "operator_pause"
            if gate.provider_calls >= policy.max_provider_calls:
                gate.stop_reason = "provider_call_budget"
            if gate.stop_reason:
                break
            if index:
                sleep(policy.case_spacing_seconds)
            if pause_check and pause_check():
                gate.stop_reason = "operator_pause"
                break
            print(json.dumps({"event": "case.started", "case_id": case.case_id}), flush=True)
            active_case_id = case.case_id
            checkpoint("running")
            content, image_hash = images[case.case_id]
            started = time.monotonic()
            try:
                result = service.run(content, case.question).model_dump(mode="json")
            except Exception as error:
                diagnostic = failure_info(error)
                if diagnostic.get("provider_status_code") == 429:
                    gate.stop_reason = "provider_429"
                    gate.retry_not_before = wall() + policy.quota_cooldown_seconds
                else:
                    gate.stop_reason = "case_exception"
                result = {
                    "status": "failed",
                    "answer_status": "verification_unavailable",
                    "query": case.question,
                    "errors": [diagnostic],
                    "calls": [],
                    "duration": time.monotonic() - started,
                }
            failed = result.get("status") in {"failed", "unverified"}
            gate.failure_streak = gate.failure_streak + 1 if failed else 0
            if not gate.stop_reason and any(
                e.get("error_category") == "configuration" for e in result.get("errors", [])
            ):
                gate.stop_reason = "model_configuration"
            if not gate.stop_reason and gate.failure_streak >= policy.max_consecutive_failures:
                gate.stop_reason = "technical_failure_streak"
                gate.retry_not_before = wall() + policy.quota_cooldown_seconds
            records.append(
                {
                    "case_id": case.case_id,
                    "case_hash": digest(case.model_dump(mode="json")),
                    "image_hash": image_hash,
                    "model_mode": model_mode,
                    "workflow_config_hash": config_hash,
                    "evaluation_policy": policy.model_dump(),
                    "result": result,
                }
            )
            seen.add(case.case_id)
            save(output, records)
            active_case_id = None
            checkpoint("paused" if gate.stop_reason else "running")
            print(
                json.dumps(
                    {
                        "event": "case.finished",
                        "case_id": case.case_id,
                        "provider_calls": gate.provider_calls,
                        "stop_reason": gate.stop_reason,
                        "credential_slot": gate.credential_slot,
                    }
                ),
                flush=True,
            )
        checkpoint(
            "paused"
            if gate.stop_reason
            else "case_limit"
            if len(seen) < len(cases)
            else "completed"
        )
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("prepare")
    setup.add_argument("--pilot", type=Path, default=ROOT / "config/evaluation/hanoi-pilot.json")
    setup.add_argument("--output", type=Path, default=ROOT / "data/evaluation/hanoi-draft.json")
    run = sub.add_parser("run")
    run.add_argument("manifest", type=Path)
    run.add_argument("--config", type=Path, default=ROOT / "config/evaluation/hanoi-paced.yaml")
    run.add_argument("--policy", type=Path, default=ROOT / "config/evaluation/pacing.yaml")
    run.add_argument("--resume", action="store_true", help="Skip all previously attempted cases")
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
        import yaml

        from workflow.service import RunService

        policy = EvaluationPolicy.model_validate(yaml.safe_load(args.policy.read_text("utf-8")))
        gate = EvaluationGate(policy)

        if args.demo:
            from api.demo import DemoManager, DemoSearch

            manager = DemoManager(load_config(args.config))
            service = RunService(manager, search_engine_factory=DemoSearch)
        else:
            from dotenv import load_dotenv

            load_dotenv()
            manager = PacedLLMManager(gate=gate, config=load_config(args.config))
            service = RunService(manager, benchmark=True)
        try:
            data = run_predictions(
                cases[: args.limit],
                service,
                output=args.output,
                policy=policy,
                gate=gate,
                model_mode="demo" if args.demo else "live",
                resume=args.resume,
            )
        finally:
            manager.close()
    if args.command != "run":
        save(args.output, data)
    print(
        f"Saved {args.output}; {len(data)} entries. Draft/demo outputs are not gold accuracy measurements."
    )


if __name__ == "__main__":
    main()
