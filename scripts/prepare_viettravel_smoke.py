"""Fetch only pinned metadata and the images needed by a small draft evaluation."""

import hashlib
import json
import re
import urllib.request
from pathlib import Path

from core.evaluation import validate_manifest
from scripts.evaluate import ROOT, read, save


def download(url, path, max_bytes):
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "HeritageVQA-evaluation/1.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            content = response.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError("Evaluation download exceeded size limit")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".download")
        temporary.write_bytes(content)
        temporary.replace(path)
    if path.stat().st_size > max_bytes:
        raise ValueError("Cached evaluation file exceeded size limit")
    return path.read_bytes()


def main():
    selection = read(ROOT / "config/evaluation/viettravel-smoke.json")
    directory = ROOT / "data/evaluation/viettravel-smoke"
    base = (
        "https://huggingface.co/datasets/"
        + selection["dataset"]
        + "/resolve/"
        + selection["revision"]
        + "/"
    )
    downloaded = {}
    for name, limit in (("metadata.jsonl", 9_000_000), ("test.jsonl", 1_000_000)):
        downloaded[name] = download(base + name, directory / name, limit)
    metadata = {
        row["id"]: row
        for row in map(json.loads, downloaded["metadata.jsonl"].decode("utf-8").splitlines())
    }
    test = {
        (row["images"][0], row["messages"][0]["content"], row["messages"][1]["content"])
        for row in map(json.loads, downloaded["test.jsonl"].decode("utf-8").splitlines())
    }
    cases, provenance = [], []
    for item in selection["cases"]:
        row = metadata[item["id"]]
        if row["split"] != "test" or row["dataset_source"] != "original":
            raise ValueError("Smoke cases must be original questions from the pinned test split")
        image = row["image"]
        if not re.fullmatch(r"VN_\d+\.jpg", image):
            raise ValueError("Unexpected upstream image name")
        if ("images/" + image, row["question"], row["answer"]) not in test:
            raise ValueError("Metadata and pinned test question disagree")
        path = directory / "images" / image
        content = download(base + "images/" + image, path, 10_000_000)
        from core.config import load_config
        from core.images import validate_image

        validate_image(content, load_config(ROOT / "config/evaluation/hanoi-paced.yaml"))
        cases.append(
            {
                "case_id": row["id"],
                "image_path": path.relative_to(ROOT).as_posix(),
                "image_family": Path(image).stem,
                "entity_group": item["entity_group"],
                "question": row["question"],
                "annotation_status": "draft",
                "split": "draft",
                "image_rights": "unverified",
                "image_source": row.get("source_image", {}).get("url"),
                "slots": [
                    {
                        "slot_id": row["id"],
                        "question": row["question"],
                        "kind": item["kind"],
                        "accepted_answers": [row["answer"]],
                    }
                ],
            }
        )
        provenance.append({**row, "image_sha256": hashlib.sha256(content).hexdigest()})
    validated = validate_manifest(cases, allow_draft=True)
    output = directory / "manifest.json"
    save(output, [case.model_dump(mode="json") for case in validated])
    save(
        directory / "provenance.json",
        {
            "dataset": selection["dataset"],
            "revision": selection["revision"],
            "upstream_split": "test",
            "annotation_status": "draft",
            "note": selection["note"],
            "download_hashes": {
                name: hashlib.sha256(body).hexdigest() for name, body in downloaded.items()
            },
            "records": provenance,
        },
    )
    print(json.dumps({"manifest": str(output), "draft_cases": len(cases)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
