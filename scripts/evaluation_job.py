"""Durable, sharded evaluation job. No training or reference answers enter model inputs."""

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from core.config import load_config
from core.evaluation import digest, validate_manifest
from core.evaluation_runtime import EvaluationGate, EvaluationPolicy, PacedLLMManager
from core.evidence import normalized_text
from core.model_errors import failure_info
from scripts.evaluate import ROOT, output_lock, read, run_predictions, save
from scripts.viettravel import ensure_image, prepare_manifest, read_spec
from workflow.service import RunService


class JobDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
    dataset_spec: str = "config/evaluation/viettravel.yaml"
    profile: str = "config/evaluation/viettravel-adapted.yaml"
    policy: str = "config/evaluation/viettravel-pacing.yaml"
    shard_size: int = Field(default=20, ge=1, le=100)
    max_provider_calls: int = Field(default=12000, ge=1, le=100000)
    max_runtime_hours: float = Field(default=168, gt=0, le=720)
    capacity_cooldown_seconds: float = Field(default=300, ge=1, le=86400)
    max_capacity_pauses: int = Field(default=3, ge=0, le=20)


def path(value):
    value = Path(value)
    return value if value.is_absolute() else ROOT / value


def engine_fingerprint():
    files = sorted(
        p
        for folder in ("core", "agents", "workflow", "scripts")
        for p in (ROOT / folder).glob("*.py")
    )
    return digest(
        {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    )


def create_job(definition, *, manifest=None, destination=None):
    spec = read_spec(path(definition.dataset_spec))
    manifest = Path(manifest) if manifest else prepare_manifest(spec, "test")
    cases = validate_manifest(read(manifest), allow_draft=True)
    provenance = manifest.with_suffix(".provenance.json")
    exposed = (
        read(provenance).get("development_exposed_test_ids", [])
        if provenance.exists()
        else spec.get("development_exposed_test_ids", [])
    )
    upstream_split = (
        read(provenance).get("upstream_split", "unknown") if provenance.exists() else "unknown"
    )
    directory = (
        Path(destination) if destination else ROOT / "reports/evaluation/jobs" / definition.job_id
    )
    directory.mkdir(parents=True, exist_ok=False)
    save(
        directory / "job.json",
        {
            "definition": definition.model_dump(),
            "manifest": str(manifest.resolve()),
            "manifest_hash": digest(read(manifest)),
            "dataset": spec["dataset"],
            "dataset_revision": spec["revision"],
            "upstream_split": upstream_split,
            "total_cases": len(cases),
            "development_exposed_test_ids": exposed,
            "profile_hash": digest(load_config(path(definition.profile)).snapshot()),
            "engine_hash": engine_fingerprint(),
            "created_at": time.time(),
        },
    )
    save(
        directory / "state.json",
        {"status": "queued", "completed_cases": 0, "total_cases": len(cases), "provider_calls": 0},
    )
    return directory


def reference_agreement(answer, references):
    predicted = normalized_text(answer or "")
    expected = [normalized_text(ref) for ref in references]
    exact = int(predicted in expected)

    def f1(reference):
        a, b = Counter(predicted.split()), Counter(reference.split())
        overlap = sum((a & b).values())
        return 2 * overlap / (sum(a.values()) + sum(b.values())) if a or b else 1.0

    return exact, max((f1(ref) for ref in expected), default=0.0)


def summarize(directory, job, *, write=True):
    cases = {case["case_id"]: case for case in read(Path(job["manifest"]))}
    provenance = Path(job["manifest"]).with_suffix(".provenance.json")
    source_kinds = (
        {row["id"]: row["dataset_source"] for row in read(provenance).get("records", [])}
        if provenance.exists()
        else {}
    )
    by_source, usage_tokens, usage_requests = {}, 0, 0
    exposed = set(job["development_exposed_test_ids"])
    statuses, technical, total, calls, fallback, em, f1, untouched = (
        Counter(),
        0,
        0,
        0,
        0,
        0,
        0.0,
        0,
    )
    for output in sorted(directory.glob("shards/*/predictions.json")):
        for record in read(output):
            result = record["result"]
            group = source_kinds.get(record["case_id"], "unclassified")
            group_stats = by_source.setdefault(
                group, {"cases": 0, "technical_failures": 0, "answer_statuses": {}}
            )
            group_stats["cases"] += 1
            status = result.get("answer_status") or result.get("status")
            group_stats["answer_statuses"][status] = (
                group_stats["answer_statuses"].get(status, 0) + 1
            )
            for call in result.get("calls", []):
                tokens = (call.get("usage") or {}).get("total_token_count")
                if isinstance(tokens, int):
                    usage_tokens += tokens
                    usage_requests += 1
            total += 1
            statuses[result.get("answer_status") or result.get("status")] += 1
            failed = result.get("status") in {"failed", "unverified"}
            technical += failed
            group_stats["technical_failures"] += failed
            if record["case_id"] not in exposed:
                untouched += 1
                # Diagnostic only. A match with an upstream string is not historical verification.
                answer = result.get("final_response") or ""
                slots = result.get("requested_slots", [])
                recognition = result.get("recognition") or {}
                if (
                    slots
                    and all(s["evidence_type"] == "identity" for s in slots)
                    and result.get("answer_status") == "answered"
                ):
                    answer = recognition.get("name") or answer
                exact, overlap = reference_agreement(
                    answer, cases[record["case_id"]]["slots"][0]["accepted_answers"]
                )
                em += exact if not failed else 0
                f1 += overlap if not failed else 0
        progress = output.with_suffix(".run.json")
        if progress.exists():
            meta = read(progress)
            calls += meta["provider_calls"]
            fallback += sum(
                e.get("credential_slot") == "fallback" for e in meta.get("provider_events", [])
            )
    result = {
        "evaluation_status": "upstream_reference_diagnostics_not_human_verified",
        "completed_cases": total,
        "total_cases": job["total_cases"],
        "provider_calls": calls,
        "credential_fallback_requests": fallback,
        "technical_failures": technical,
        "total_tokens_with_usage": usage_tokens,
        "logical_calls_with_usage": usage_requests,
        "by_dataset_source": by_source,
        "answer_statuses": dict(statuses),
        "cases_not_known_exposed_attempted": untouched,
        "upstream_split": job.get("upstream_split", "unknown"),
        "development_exposed_test_ids": job["development_exposed_test_ids"],
        "reference_exact_match": em / untouched if untouched else None,
        "reference_token_f1": f1 / untouched if untouched else None,
        "note": "String agreement only; failed cases score zero. Source URL checks cannot prove image/entity independence. No human-reviewed accuracy claim.",
    }
    if write:
        save(directory / "summary.json", result)
    return result


def run_job(directory, *, demo=False, resume=False, sleep=time.sleep):
    directory = Path(directory).resolve()
    job = read(directory / "job.json")
    definition = JobDefinition.model_validate(job["definition"])
    state = read(directory / "state.json")
    if state.get("model_mode") and state["model_mode"] != ("demo" if demo else "live"):
        raise ValueError("Cannot mix demo and live records in one job")
    if state["status"] not in {"queued", "completed"} and not resume:
        raise ValueError("Existing job requires --resume; inspect its checkpoint first")
    if state["status"] == "completed":
        return state
    if digest(read(Path(job["manifest"]))) != job["manifest_hash"]:
        raise ValueError("Job manifest changed")
    if job.get("engine_hash") and job["engine_hash"] != engine_fingerprint():
        raise ValueError("Engine code changed; preserve this job and create a separate comparison")
    config = load_config(path(definition.profile))
    if digest(config.snapshot()) != job["profile_hash"]:
        raise ValueError("Workflow configuration changed; create a separate comparison job")
    cases = validate_manifest(read(Path(job["manifest"])), allow_draft=True)
    policy = EvaluationPolicy.model_validate(
        yaml.safe_load(path(definition.policy).read_text("utf-8"))
    )
    spec = read_spec(path(definition.dataset_spec))
    if spec["dataset"] != job["dataset"] or spec["revision"] != job["dataset_revision"]:
        raise ValueError("Dataset specification changed")
    started, capacity_pauses = time.monotonic(), 0
    state.update(status="running", worker_pid=os.getpid(), model_mode="demo" if demo else "live")

    def update(**fields):
        state.update(fields, updated_at=time.time())
        save(directory / "state.json", state)

    with output_lock(directory / "worker"):
        if resume and (directory / "PAUSE").is_file():
            (directory / "PAUSE").unlink()
        update()
        try:
            for offset in range(0, len(cases), definition.shard_size):
                if (directory / "PAUSE").exists():
                    update(status="paused", stop_reason="operator_pause")
                    break
                summary = summarize(directory, job)
                if summary["provider_calls"] >= definition.max_provider_calls:
                    update(status="paused", stop_reason="job_provider_budget", **summary)
                    break
                if time.monotonic() - started > definition.max_runtime_hours * 3600:
                    update(status="paused", stop_reason="runtime_budget", **summary)
                    break
                shard = cases[offset : offset + definition.shard_size]
                current = directory / "shards" / f"{offset // definition.shard_size:04d}"
                current.mkdir(parents=True, exist_ok=True)
                output = current / "predictions.json"
                meta = (
                    read(output.with_suffix(".run.json"))
                    if output.with_suffix(".run.json").exists()
                    else {}
                )
                if meta.get("status") == "completed":
                    continue
                update(
                    active_shard=str(current.relative_to(directory)),
                    phase="preparing_images",
                    **summary,
                )
                if not demo:
                    for image in dict.fromkeys(Path(c.image_path).name for c in shard):
                        ensure_image(spec, image)
                while True:
                    previous = (
                        read(output.with_suffix(".run.json"))
                        if output.with_suffix(".run.json").exists()
                        else {}
                    )
                    wait = max(0, (previous.get("retry_not_before") or 0) - time.time())
                    if wait:
                        update(phase="cooldown", cooldown_seconds=wait)
                        sleep(wait)
                    summary = summarize(directory, job)
                    remaining = definition.max_provider_calls - summary["provider_calls"]
                    if remaining <= 0:
                        update(status="paused", stop_reason="job_provider_budget", **summary)
                        return state
                    batch_policy = policy.model_copy(
                        update={
                            "max_cases": definition.shard_size,
                            "max_provider_calls": min(
                                policy.max_provider_calls,
                                remaining + previous.get("provider_calls", 0),
                            ),
                        }
                    )
                    gate = EvaluationGate(batch_policy)
                    previous_starts = [
                        timestamp
                        for progress_file in directory.glob("shards/*/predictions.run.json")
                        for timestamp in read(progress_file).get("request_start_times", [])[-1:]
                    ]
                    if previous_starts:
                        delay = max(
                            0, max(previous_starts) + policy.request_spacing_seconds - time.time()
                        )
                        gate.defer(delay)
                    gate.credential_slot = previous.get(
                        "credential_slot", state.get("credential_slot", "primary")
                    )
                    if demo:
                        from api.demo import DemoManager, DemoSearch

                        manager = DemoManager(config)
                        service = RunService(manager, search_engine_factory=DemoSearch)
                    else:
                        manager = PacedLLMManager(gate=gate, config=config)
                        service = RunService(manager, benchmark=True)
                    update(phase="evaluating")
                    try:
                        run_predictions(
                            shard,
                            service,
                            output=output,
                            policy=batch_policy,
                            gate=gate,
                            model_mode="demo" if demo else "live",
                            resume=output.exists(),
                            sleep=sleep,
                            pause_check=lambda: (directory / "PAUSE").exists(),
                        )
                    finally:
                        manager.close()
                    summary = summarize(directory, job)
                    update(credential_slot=gate.credential_slot, **summary)
                    if (
                        gate.stop_reason == "provider_503"
                        and capacity_pauses < definition.max_capacity_pauses
                    ):
                        capacity_pauses += 1
                        update(phase="capacity_cooldown", capacity_pauses=capacity_pauses)
                        sleep(
                            min(
                                86400,
                                definition.capacity_cooldown_seconds * (2 ** (capacity_pauses - 1)),
                            )
                        )
                        continue
                    if gate.stop_reason:
                        update(
                            status="paused",
                            stop_reason=gate.stop_reason,
                            retry_not_before=gate.retry_not_before,
                        )
                        return state
                    break
                if offset + definition.shard_size < len(cases):
                    sleep(policy.case_spacing_seconds)
            else:
                update(status="completed", phase="finished", **summarize(directory, job))
        except Exception as error:
            update(status="paused", stop_reason="worker_error", error=failure_info(error))
            raise
    return state


def main():
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument(
        "--definition", type=Path, default=ROOT / "config/evaluation/viettravel-job.yaml"
    )
    create.add_argument("--manifest", type=Path, help="Existing pinned dataset subset manifest")
    for command in ("run", "status", "pause"):
        p = commands.add_parser(command)
        p.add_argument("directory", type=Path)
        if command == "run":
            mode = p.add_mutually_exclusive_group(required=True)
            mode.add_argument("--live", action="store_true")
            mode.add_argument("--demo", action="store_true")
            p.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.command == "create":
        definition = JobDefinition.model_validate(
            yaml.safe_load(args.definition.read_text("utf-8"))
        )
        print(json.dumps({"job_directory": str(create_job(definition, manifest=args.manifest))}))
    elif args.command == "run":
        print(
            json.dumps(
                run_job(args.directory, demo=args.demo, resume=args.resume), ensure_ascii=True
            )
        )
    elif args.command == "pause":
        if not (args.directory / "job.json").is_file():
            parser.error("Unknown job directory")
        (args.directory / "PAUSE").write_text("Pause after current case\n", encoding="utf-8")
        print(json.dumps({"pause_requested": True}))
    else:
        state = read(args.directory / "state.json")
        state["live_totals"] = summarize(
            args.directory, read(args.directory / "job.json"), write=False
        )
        if state.get("active_shard"):
            progress = args.directory / state["active_shard"] / "predictions.run.json"
            if progress.exists():
                current = read(progress)
                state["active_shard_progress"] = {
                    key: current.get(key)
                    for key in (
                        "status",
                        "active_case_id",
                        "provider_calls",
                        "credential_slot",
                        "stop_reason",
                        "retry_not_before",
                    )
                }
                state["active_shard_progress"]["completed_cases"] = len(
                    current.get("completed_case_ids", [])
                )
        print(json.dumps(state, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
