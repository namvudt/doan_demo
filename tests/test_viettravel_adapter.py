from scripts.prepare_viettravel_small import select_rows
from scripts.viettravel import canonical_image_source, exposed_test_ids


def test_original_and_thumbnail_source_share_family_despite_different_ids():
    original = {
        "source_image": {"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Example.jpg"}
    }
    thumbnail = {
        "source_image": {
            "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Example.jpg/1200px-Example.jpg"
        }
    }
    assert canonical_image_source(original) == canonical_image_source(thumbnail)
    other = {
        "source_image": {"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Other.jpg"}
    }
    rows = [
        {**original, "id": "dev", "split": "validation"},
        {**thumbnail, "id": "test-overlap", "split": "test"},
        {**other, "id": "test-new", "split": "test"},
    ]
    assert exposed_test_ids({"calibration_case_ids": ["dev"]}, rows) == ["test-overlap"]


def test_missing_source_is_not_a_shared_family():
    rows = [{"id": "dev", "split": "validation"}, {"id": "test", "split": "test"}]
    assert exposed_test_ids({"calibration_case_ids": ["dev"]}, rows) == []


def test_small_selection_is_reproducible_stratified_and_excludes_calibration():
    rows = []
    for source in ("original", "kg_generated", "graph_generated"):
        for i in range(4):
            rows.append(
                {"id": f"{source}-{i}", "image": f"{source}-{i}.jpg", "dataset_source": source}
            )
    spec = {"calibration_case_ids": ["original-0"]}
    chosen = select_rows(spec, rows)
    assert chosen == select_rows(spec, rows)
    assert len(chosen) == len({r["image"] for r in chosen}) == 6
    assert "original-0" not in {r["id"] for r in chosen}
    assert all(
        sum(r["dataset_source"] == category for r in chosen) == 2
        for category in ("original", "kg_generated", "graph_generated")
    )
