"""Create a fixed, stratified development subset without selecting on reference answers."""

import json
import random

from scripts.viettravel import canonical_image_source, load_split, prepare_manifest, read_spec


def select_rows(spec, rows, *, seed=20261127, per_source=2):
    calibration = set(spec.get("calibration_case_ids", []))
    excluded_sources = {canonical_image_source(r) for r in rows if r["id"] in calibration} - {""}
    pool = [
        r
        for r in rows
        if r["id"] not in calibration and canonical_image_source(r) not in excluded_sources
    ]
    rng = random.Random(seed)
    selected, used_images, used_sources = [], set(), set()
    for source in ("original", "kg_generated", "graph_generated"):
        candidates = [r for r in pool if r["dataset_source"] == source]
        rng.shuffle(candidates)
        count = 0
        for row in candidates:
            origin = canonical_image_source(row)
            if row["image"] in used_images or (origin and origin in used_sources):
                continue
            selected.append(row)
            used_images.add(row["image"])
            if origin:
                used_sources.add(origin)
            count += 1
            if count == per_source:
                break
        if count != per_source:
            raise ValueError("Insufficient distinct images for stratified selection")
    rng.shuffle(selected)
    return selected


def main():
    spec = read_spec()
    rows = load_split(spec, "validation")
    selected = select_rows(spec, rows)
    manifest = prepare_manifest(
        spec,
        "validation",
        selected_ids=[r["id"] for r in selected],
        output_name="validation-small-v1",
    )
    print(
        json.dumps(
            {
                "manifest": str(manifest),
                "split": "validation",
                "seed": 20261127,
                "cases": [{"id": r["id"], "source": r["dataset_source"]} for r in selected],
            }
        )
    )


if __name__ == "__main__":
    main()
