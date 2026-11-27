import json
from pathlib import Path

import pytest
import yaml

from scripts.evaluate import save
from scripts.evaluation_job import JobDefinition, create_job, reference_agreement, run_job


def test_reference_match_is_a_string_diagnostic_only():
    assert reference_agreement("Màu đỏ.", ["màu đỏ"]) == (1, 1)
    assert reference_agreement("", ["Màu đỏ"]) == (0, 0)
    assert reference_agreement("Đỏ", ["Màu đỏ"])[1] < 1


def test_sharded_demo_job_completes_and_resume_does_not_repeat(tmp_path):
    policy = tmp_path / "pacing.yaml"
    policy.write_text(
        yaml.safe_dump(
            {
                "request_spacing_seconds": 0,
                "case_spacing_seconds": 0,
                "max_cases": 1,
                "max_provider_calls": 20,
            }
        ),
        encoding="utf-8",
    )
    image = Path("samples/chua_huong.jpg").resolve()
    manifest = tmp_path / "manifest.json"
    save(
        manifest,
        [
            {
                "case_id": f"synthetic-{i}",
                "image_path": str(image),
                "image_family": "synthetic",
                "entity_group": "synthetic",
                "question": "Identify this monument",
                "slots": [
                    {
                        "slot_id": "s",
                        "question": "Name?",
                        "kind": "identity",
                        "accepted_answers": ["synthetic reference"],
                    }
                ],
            }
            for i in range(2)
        ],
    )
    definition = JobDefinition(job_id="synthetic-job", policy=str(policy), shard_size=1)
    directory = create_job(definition, manifest=manifest, destination=tmp_path / "job")
    (directory / "PAUSE").write_text("synthetic pause", encoding="utf-8")
    paused = run_job(directory, demo=True, sleep=lambda _: None)
    assert paused["status"] == "paused" and paused["completed_cases"] == 0
    result = run_job(directory, demo=True, resume=True, sleep=lambda _: None)
    assert result["status"] == "completed" and result["completed_cases"] == 2
    before = [p.read_bytes() for p in sorted(directory.glob("shards/*/predictions.json"))]
    run_job(directory, demo=True, resume=True, sleep=lambda _: None)
    assert [p.read_bytes() for p in sorted(directory.glob("shards/*/predictions.json"))] == before
    summary = json.loads((directory / "summary.json").read_text())
    assert summary["evaluation_status"] == "upstream_reference_diagnostics_not_human_verified"
    assert summary["provider_calls"] == 0
    with pytest.raises(ValueError, match="mix demo and live"):
        run_job(directory, demo=False, resume=True, sleep=lambda _: None)


def test_job_definition_rejects_unbounded_or_path_like_ids():
    with pytest.raises(ValueError):
        JobDefinition(job_id="../escape")
    with pytest.raises(ValueError):
        JobDefinition(job_id="x", max_provider_calls=0)
