"""Pinned VietTravelVQA adapter; upstream references never enter workflow inputs."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

from core.evaluation import validate_manifest
from scripts.evaluate import ROOT, save
from scripts.prepare_viettravel_smoke import download

SPEC = ROOT / "config/evaluation/viettravel.yaml"


def read_spec(path=SPEC):
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", spec["dataset"]):
        raise ValueError("Unexpected dataset repository")
    if not re.fullmatch(r"[a-f0-9]{40}", spec["revision"]):
        raise ValueError("Dataset revision must be pinned")
    return spec


def directory(spec):
    return ROOT / "data/evaluation/viettravel" / spec["revision"]


def base_url(spec):
    return f"https://huggingface.co/datasets/{spec['dataset']}/resolve/{spec['revision']}/"


def canonical_image_source(row):
    url = (row.get("source_image") or {}).get("url") or ""
    parts = urlsplit(url)
    match = re.search(r"/wikipedia/commons/(?:thumb/)?[^/]+/[^/]+/([^/]+)", unquote(parts.path))
    if parts.netloc.lower() == "upload.wikimedia.org" and match:
        return "wikimedia:" + match[1].casefold()
    return parts.netloc.lower() + unquote(parts.path) if parts.netloc else ""


def exposed_test_ids(spec, rows):
    selected = set(spec.get("calibration_case_ids", [])) | set(
        spec.get("development_exposed_test_ids", [])
    )
    seen_sources = {canonical_image_source(row) for row in rows if row["id"] in selected} - {""}
    return [
        row["id"]
        for row in rows
        if row["split"] == "test"
        and (row["id"] in selected or canonical_image_source(row) in seen_sources)
    ]


def load_split(spec, split):
    if split not in {"train", "validation", "test"}:
        raise ValueError("Unexpected split")
    root = directory(spec)
    for name in ("metadata.jsonl", split + ".jsonl"):
        path = root / name
        # Reuse only the earlier, identically pinned smoke cache.
        previous = ROOT / "data/evaluation/viettravel-smoke" / name
        if (
            not path.exists()
            and previous.is_file()
            and spec["revision"] == "75d72d93f12f40756e5dfa0775236d3d78483fa4"
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(previous.read_bytes())
        download(base_url(spec) + name, path, 12_000_000)
    metadata = [
        json.loads(line) for line in (root / "metadata.jsonl").read_text("utf-8").splitlines()
    ]
    rows = [row for row in metadata if row["split"] == split]
    raw = [json.loads(line) for line in (root / (split + ".jsonl")).read_text("utf-8").splitlines()]
    expected = Counter(("images/" + r["image"], r["question"], r["answer"]) for r in rows)
    actual = Counter(
        (r["images"][0], r["messages"][0]["content"], r["messages"][1]["content"]) for r in raw
    )
    if expected != actual or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Pinned metadata and split disagree")
    return rows


def ensure_image(spec, image):
    if not re.fullmatch(r"VN_\d+\.(?:jpg|jpeg|png|webp)", image, re.IGNORECASE):
        raise ValueError("Unexpected image path")
    target = directory(spec) / "images" / image
    previous = ROOT / "data/evaluation/viettravel-smoke/images" / image
    if (
        not target.exists()
        and previous.is_file()
        and spec["revision"] == "75d72d93f12f40756e5dfa0775236d3d78483fa4"
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(previous.read_bytes())
    return download(base_url(spec) + "images/" + image, target, 10_000_000)


def prepare_manifest(spec, split, *, selected_ids=None, download_images=False, output_name=None):
    rows = load_split(spec, split)
    if selected_ids is not None:
        by_id = {row["id"]: row for row in rows}
        if not set(selected_ids) <= by_id.keys():
            raise ValueError("Selection contains IDs outside the requested split")
        rows = [by_id[identifier] for identifier in selected_ids]
    cases = []
    for row in rows:
        image = row["image"]
        if not re.fullmatch(r"VN_\d+\.(?:jpg|jpeg|png|webp)", image, re.IGNORECASE):
            raise ValueError("Unexpected image name")
        if download_images:
            ensure_image(spec, image)
        cases.append(
            {
                "case_id": row["id"],
                "image_path": (directory(spec) / "images" / image).relative_to(ROOT).as_posix(),
                "image_family": Path(image).stem,
                "entity_group": row.get("wikidata_qid") or Path(image).stem,
                "question": row["question"],
                "annotation_status": "draft",
                "split": "draft",
                "image_rights": "unverified",
                "image_source": (row.get("source_image") or {}).get("url"),
                "slots": [
                    {
                        "slot_id": row["id"],
                        "question": row["question"],
                        "kind": "mixed",
                        "accepted_answers": [row["answer"]],
                    }
                ],
            }
        )
    validated = validate_manifest(cases, allow_draft=True)
    name = output_name or ("calibration" if selected_ids is not None else split)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("Unexpected manifest name")
    output = directory(spec) / (name + ".json")
    save(output, [case.model_dump(mode="json") for case in validated])
    save(
        output.with_suffix(".provenance.json"),
        {
            "dataset": spec["dataset"],
            "revision": spec["revision"],
            "upstream_split": split,
            "annotation_status": "draft",
            "case_count": len(rows),
            "image_count": len({r["image"] for r in rows}),
            "dataset_sources": dict(Counter(r["dataset_source"] for r in rows)),
            "development_exposed_test_ids": exposed_test_ids(
                spec,
                [
                    json.loads(line)
                    for line in (directory(spec) / "metadata.jsonl").read_text("utf-8").splitlines()
                ],
            ),
            "metadata_sha256": hashlib.sha256(
                (directory(spec) / "metadata.jsonl").read_bytes()
            ).hexdigest(),
            "records": rows,
        },
    )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument("--split", choices=("train", "validation", "test"), default="validation")
    parser.add_argument("--calibration", action="store_true")
    parser.add_argument("--download-images", action="store_true")
    args = parser.parse_args()
    spec = read_spec(args.spec)
    if args.calibration and args.split != spec["calibration_split"]:
        parser.error("Calibration must use the configured development split")
    output = prepare_manifest(
        spec,
        args.split,
        selected_ids=spec["calibration_case_ids"] if args.calibration else None,
        download_images=args.download_images,
    )
    print(json.dumps({"manifest": str(output), "split": args.split}, ensure_ascii=True))


if __name__ == "__main__":
    main()
