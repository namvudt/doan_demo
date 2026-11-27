"""Entity labels must not mix a question's answer with its photographed subject."""

import json

import pytest

from core.entities import EntityCatalog

VIETNAM_CATALOG = "config/heritage/vietnam.entities.json"


@pytest.mark.parametrize("answer", ["Việt Nam", "Vietnam", "Trung Quốc", "2", "2.5", "có", "không"])
def test_country_and_answer_values_are_not_image_candidates(answer):
    catalog = EntityCatalog()
    candidates = catalog.candidates(["Chùa Thiên Trù", answer])
    assert [c["entity_id"] for c in candidates] == ["hanoi:chua-thien-tru"]


def test_unknown_place_is_allowed_but_known_administrative_label_is_not_image_candidate():
    catalog = EntityCatalog(VIETNAM_CATALOG)
    assert catalog.candidates(["Chùa độc lập ABC"])[0]["entity_type"] == "unknown"
    assert catalog.candidates(["Sơn La"]) == []
    assert (
        catalog.candidates(["Sơn La"], allowed_types={"administrative_area"})[0]["entity_id"]
        == "admin:son-la"
    )
    assert catalog.candidates(["Nhà tù Sơn La"], allowed_types={"protected_area"}) == []


def test_aliases_and_validated_location_qualifiers_resolve_to_one_id():
    catalog = EntityCatalog(VIETNAM_CATALOG)
    candidates = catalog.candidates(["Lý Sơn", "Đảo Lý Sơn, Quảng Ngãi", "Ly Son Island"])
    assert len(candidates) == 1
    assert candidates[0]["entity_id"] == "place:ly-son"
    assert catalog.resolve("Đảo Lý Sơn (Quảng Ngãi)") == "place:ly-son"
    assert catalog.resolve("Đảo Lý Sơn (Hà Nội)") is None


def test_catalog_inheritance_preserves_hanoi_components():
    catalog = EntityCatalog(VIETNAM_CATALOG)
    assert catalog.resolve("Gác Khuê Văn") == "hanoi:khue-van-cac"
    assert "hanoi:van-mieu" in catalog.ancestors("hanoi:khue-van-cac")
    assert catalog.resolve("Văn Miếu (Hà Nội)") == "hanoi:van-mieu"
    assert catalog.resolve("Gác Khuê Văn (Hà Nội)") == "hanoi:khue-van-cac"
    assert catalog.resolve("Chùa Thiên Trù (Hương Sơn, Mỹ Đức, Hà Nội)") == "hanoi:chua-thien-tru"


def test_geographic_place_is_not_an_alias_or_identity_parent_of_park():
    catalog = EntityCatalog(VIETNAM_CATALOG)
    place, park = catalog.candidates(["Mũi Cà Mau", "VQG Mũi Cà Mau"])
    assert place["entity_id"] != park["entity_id"]
    assert catalog.most_specific([place["entity_id"], park["entity_id"]]) is None
    assert catalog.entities[place["entity_id"]]["relations"][0] == {
        "type": "located_within",
        "target_id": "protected:mui-ca-mau",
        "note": "Geographic relation, not an alias or proof of image identity.",
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Lý Sơn trong ảnh thuộc quốc gia nào?", "place:ly-son"),
        ("Nhà tù Sơn La nằm ở Sơn La, và Sơn La thuộc quốc gia nào?", "admin:son-la"),
        ("Địa danh Lý Sơn thuộc quốc gia nào?", "place:ly-son"),
        ("Chùa Thiên Trù được xây dựng khi nào?", "hanoi:chua-thien-tru"),
    ],
)
def test_explicit_question_subject_does_not_supply_an_answer(query, expected):
    catalog = EntityCatalog(VIETNAM_CATALOG)
    subject = catalog.extract_subject(query)
    assert subject["entity_id"] == expected
    assert subject["subject_basis"] == "explicit_question"
    assert not {"country", "answer", "recognized", "identity_resolved"} & subject.keys()


@pytest.mark.parametrize(
    "query",
    [
        "Công trình này thuộc quốc gia nào?",
        "Ngôi chùa trong ảnh thuộc quốc gia nào?",
        "Đây có thể là Lý Sơn, Lý Sơn thuộc quốc gia nào?",
        "Có phải đây là Chùa Hương không?",
        "Cho biết khởi dựng và trùng tu khi nào?",
        "Khởi dựng và trùng tu khi nào?",
        "Hãy cho tôi biết khởi dựng và trùng tu khi nào?",
        "Di tích này được xây dựng khi nào?",
        "Nơi gần công trình thuộc quốc gia nào?",
        "Ngôi chùa cổ thuộc quốc gia nào?",
        "Nhà tù cũ được xây dựng khi nào?",
    ],
)
def test_generic_or_tentative_subject_is_not_promoted(query):
    assert EntityCatalog(VIETNAM_CATALOG).extract_subject(query) is None


def test_subject_extraction_is_configurable_without_relaxing_image_identity():
    catalog = EntityCatalog(VIETNAM_CATALOG)
    assert catalog.extract_subject("Lý Sơn thuộc nước nào?", enabled=False) is None
    subject = catalog.extract_subject(
        "Hỏi về: Nhà tù Sơn La?", patterns=[r"^Hỏi về: (?P<subject>[^?]+)"]
    )
    assert subject["entity_id"] == "heritage:son-la-prison"
    assert catalog.extract_subject("Đảo XYZ thuộc nước nào?")["entity_type"] == "unknown"
    assert (
        catalog.extract_subject("Hãy cho tôi biết Lý Sơn thuộc nước nào?")["entity_id"]
        == "place:ly-son"
    )


def test_source_country_mention_does_not_steal_landmark_binding():
    catalog = EntityCatalog(VIETNAM_CATALOG)
    landmark = catalog.candidates(["Đảo Lý Sơn"])[0]
    country = catalog.candidates(["Việt Nam"], allowed_types={"country"})[0]
    text = "Đảo Lý Sơn, Quảng Ngãi, Việt Nam xuất hiện trong đoạn nguồn."
    assert catalog.source_entity([landmark, country], text) == landmark["entity_id"]
    assert catalog.source_entity([landmark, country], "Việt Nam") is None


def test_selected_question_subject_must_actually_be_mentioned_by_source():
    catalog = EntityCatalog(VIETNAM_CATALOG)
    monument = catalog.candidates(["Nhà tù Sơn La"])[0]
    subject = catalog.extract_subject("Sơn La thuộc quốc gia nào?")
    candidates = [monument, subject]
    assert (
        catalog.source_entity(
            candidates, "Nhà tù Sơn La nằm ở Sơn La.", selected_entity_id=subject["entity_id"]
        )
        == "admin:son-la"
    )
    assert (
        catalog.source_entity(
            candidates, "Nguồn nói về một thành phố khác.", selected_entity_id=subject["entity_id"]
        )
        is None
    )


def test_distinct_places_cannot_be_forced_into_same_source_entity():
    catalog = EntityCatalog(VIETNAM_CATALOG)
    candidates = catalog.candidates(["Mũi Cà Mau", "Vườn quốc gia Mũi Cà Mau"])
    assert catalog.source_entity(candidates, "Mũi Cà Mau và Vườn quốc gia Mũi Cà Mau") is None


def test_region_name_inside_park_name_is_not_a_separate_region_mention():
    catalog = EntityCatalog(VIETNAM_CATALOG)
    place, park = catalog.candidates(["Mũi Cà Mau", "Vườn quốc gia Mũi Cà Mau"])
    text = "Vườn quốc gia Mũi Cà Mau bảo tồn hệ sinh thái."
    assert (
        catalog.source_entity([place, park], text, selected_entity_id=place["entity_id"])
        == park["entity_id"]
    )
    assert catalog.source_mentions(place, text)  # Broad retrieval can still discover it.
    assert not catalog.source_mentions(place, text, independent=True)


def test_province_component_in_monument_name_does_not_bind_province_subject():
    catalog = EntityCatalog(VIETNAM_CATALOG)
    monument = catalog.candidates(["Nhà tù Sơn La"])[0]
    subject = catalog.extract_subject("Sơn La thuộc quốc gia nào?")
    assert (
        catalog.source_entity(
            [monument, subject],
            "Nhà tù Sơn La là một di tích.",
            selected_entity_id=subject["entity_id"],
        )
        == monument["entity_id"]
    )


def test_catalog_cycles_are_rejected(tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_text(json.dumps({"extends": "second.json", "entities": []}), encoding="utf-8")
    second.write_text(json.dumps({"extends": "first.json", "entities": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="inheritance cycle"):
        EntityCatalog(first)
