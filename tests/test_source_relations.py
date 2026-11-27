"""Quoted relational support must connect the claimed subject and object."""

import pytest

from core.relations import country_relation_signal, validate_source_relation
from core.search import relevant_passage

QUESTION = "Tỉnh Lam thuộc quốc gia nào?"
CLAIM = "Tỉnh Lam thuộc quốc gia Nước Thử."


@pytest.mark.parametrize(
    "quote",
    [
        "Tỉnh Lam thuộc quốc gia Nước Thử.",
        "Tỉnh Lam là một tỉnh nằm ở miền núi phía bắc của Nước Thử.",
        "Tỉnh Lam nằm ở Nước Thử.",
        "Tỉnh Lam is a province in Nước Thử.",
        "Tỉnh Lam là một tỉnh miền núi, vùng cao ở vùng Tây Bắc Bộ, Nước Thử.",
    ],
)
def test_direct_country_relation_is_supported(quote):
    assert validate_source_relation(CLAIM, quote, subject="Tỉnh Lam", question=QUESTION) is None


@pytest.mark.parametrize(
    "quote",
    [
        "Nhà tù Tỉnh Lam giam giữ người làm cách mạng của Nước Thử.",
        "Nhà tù Tỉnh Lam thuộc quốc gia Nước Thử.",
        "Tỉnh Lam có nhiều cây. Nước Thử có nhiều núi.",
        "Tỉnh Lam thuộc quốc gia Nước Khác.",
        "Tỉnh Lam không thuộc quốc gia Nước Thử.",
        "Người ở Tỉnh Lam có quốc tịch Nước Thử.",
        "Một người từ Tỉnh Lam tham gia hội đồng quốc gia Nước Thử.",
        "Nước Thử.",
        "",
    ],
)
def test_country_mention_and_subject_substring_do_not_prove_location(quote):
    assert (
        validate_source_relation(CLAIM, quote, subject="Tỉnh Lam", question=QUESTION)
        == "relation_quote_mismatch"
    )


def test_frozen_son_la_prison_quote_does_not_support_province_country():
    assert (
        validate_source_relation(
            "Tỉnh Sơn La thuộc quốc gia Việt Nam.",
            "nhà tù Sơn La đã được người Pháp xây dựng trong thời kỳ Pháp thuộc nhằm mục tiêu "
            "giam cầm những người làm cách mạng của Việt Nam.",
            subject={"name": "Sơn La", "aliases": ["Tỉnh Sơn La"]},
            question="Nhà tù Sơn La nằm ở Sơn La, và Sơn La thuộc quốc gia nào?",
        )
        == "relation_quote_mismatch"
    )


def test_subject_aliases_and_extra_claim_clause_do_not_change_country_object():
    assert (
        validate_source_relation(
            "Đảo Lam thuộc chủ quyền Nước Thử, là đơn vị hành chính thuộc tỉnh Minh.",
            "Lam là một đảo ở miền bắc của Nước Thử.",
            subject={"name": "Đảo Lam", "aliases": ["Lam"]},
            question="Đảo Lam trong ảnh thuộc quốc gia nào?",
        )
        is None
    )


def test_other_relations_are_left_to_existing_verifier():
    assert (
        validate_source_relation(
            "Công trình khởi dựng năm 1900.",
            "Một câu chưa kiểm chứng.",
            subject="Site A",
            question="Công trình được khởi dựng năm nào?",
        )
        is None
    )


def test_unknown_subject_cannot_be_proven_by_country_value_alone():
    assert (
        validate_source_relation(
            CLAIM,
            "Tỉnh Lam thuộc quốc gia Nước Thử.",
            subject=None,
            question=QUESTION,
        )
        == "relation_quote_mismatch"
    )


def test_country_relation_syntax_is_configurable():
    rules = {
        "country": {
            "question_patterns": [r"custom country question"],
            "claim_object_patterns": [r"^{subject} country (?P<object>[\w ]+)$"],
            "quote_patterns": [r"^{subject} has country {object}$"],
        }
    }
    assert (
        validate_source_relation(
            "Place A country Nation B",
            "Place A has country Nation B",
            subject="Place A",
            question="Custom country question?",
            rules=rules,
        )
        is None
    )


def test_nearest_without_a_comparison_scope_cannot_be_asserted():
    assert (
        validate_source_relation(
            "Đảo B ở gần nhất Site A.",
            "Đảo B ở gần nhất Site A.",
            subject="Site A",
            question="Địa danh gần Site A nhất là gì?",
        )
        == "nearest_scope_required"
    )


def test_nearest_scoped_question_requires_nearest_claim_and_quote():
    question = "Trong số các điểm đến được liệt kê, nơi gần nhất Site A là gì?"
    assert (
        validate_source_relation(
            "Site A có rừng ven biển.",
            "Site A có rừng ven biển.",
            subject="Site A",
            question=question,
        )
        == "nearest_relation_required"
    )
    assert (
        validate_source_relation(
            "Đảo B gần nhất Site A.",
            "Đảo B cách Site A 8 km.",
            subject="Site A",
            question=question,
        )
        == "nearest_relation_required"
    )
    assert (
        validate_source_relation(
            "Đảo B gần nhất Site A.",
            "Trong danh sách đã nêu, Đảo B gần nhất Site A.",
            subject="Site A",
            question=question,
        )
        is None
    )


def test_country_intro_outranks_dense_terrain_without_losing_locator():
    lead = "Tỉnh Lam là một tỉnh miền núi phía bắc của Nước Thử."
    terrain = "Tỉnh Lam nằm ở vùng núi. Tỉnh Lam có thành phố, địa hình và nhiều tỉnh khác. " * 10
    text = lead + "\n\n== Địa hình ==\n\n" + terrain
    snippet, locator = relevant_passage(
        text,
        QUESTION,
        240,
        relation="country",
        relation_subject=["Tỉnh Lam"],
        preferred_terms=["thuộc", "tỉnh", "thành phố", "nằm ở"],
    )
    assert lead in snippet
    _, start, end = locator.split(":")
    assert text[int(start) : int(end)] == snippet and len(snippet) <= 240


def test_country_retrieval_signal_rejects_people_biography():
    assert not country_relation_signal(
        "Nhà tù Tỉnh Lam giam người làm cách mạng của Nước Thử.", subject=["Tỉnh Lam"]
    )
    assert country_relation_signal(
        "Tỉnh Lam là một tỉnh phía bắc của Nước Thử.", subject=["Tỉnh Lam"]
    )


@pytest.mark.parametrize(
    "geographic_class",
    [
        "đặc khu",
        "huyện đảo",
        "xã",
        "phường",
        "khu bảo tồn",
        "vườn quốc gia",
        "district",
        "special administrative region",
    ],
)
def test_generic_current_administrative_classes_preserve_country_target(geographic_class):
    assert (
        validate_source_relation(
            "Lam thuộc quốc gia Nước Thử.",
            f"Lam là một {geographic_class} của Nước Thử.",
            subject="Lam",
            question="Lam thuộc quốc gia nào?",
        )
        is None
    )


def test_administrative_reorganization_without_country_is_not_country_evidence():
    assert (
        validate_source_relation(
            "Lam thuộc quốc gia Nước Thử.",
            "Huyện đảo Lam được sắp xếp thành đặc khu Lam.",
            subject={"name": "Lam", "aliases": ["Huyện đảo Lam", "Đặc khu Lam"]},
            question="Lam thuộc quốc gia nào?",
        )
        == "relation_quote_mismatch"
    )


def test_nearest_words_for_another_target_do_not_prove_claimed_target():
    assert (
        validate_source_relation(
            "Đảo B gần nhất Site A.",
            "Trong danh sách đã nêu, Đảo C gần nhất Site A.",
            subject="Site A",
            question="Trong số các điểm đến được liệt kê, nơi gần nhất Site A là gì?",
        )
        == "nearest_relation_required"
    )
