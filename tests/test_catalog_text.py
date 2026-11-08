import json
from pathlib import Path

from BOOKzMA.services.catalog_text import (
    build_search_document,
    normalize_catalog_text,
    search_document_hash,
)


def test_catalog_normalization_unifies_persian_arabic_forms_and_digits():
    assert normalize_catalog_text("کتاب‌ها کتابها کتاب ها") == "کتاب ها کتاب ها کتاب ها"
    assert normalize_catalog_text("ي ی ى") == "ی ی ی"
    assert normalize_catalog_text("ك ک") == "ک ک"
    assert normalize_catalog_text("۱۲۳ ١٢٣ 123") == "123 123 123"


def test_catalog_search_document_cleans_filename_and_preserves_display_name():
    document = build_search_document(
        message_id=42,
        file_name="جزوه_درس_متره_برآورد.pdf",
        caption_preview="مرور نکات مهم",
        caption_search="مرور نکات مهم",
        file_size=2048,
        mime_type="application/pdf",
        media_type="Document",
        posted_at="2026-11-07T10:00:00+00:00",
    )

    assert document["id"] == 42
    assert document["title"] == "جزوه درس متره برآورد"
    assert document["file_name"] == "جزوه_درس_متره_برآورد.pdf"
    assert document["caption"] == "مرور نکات مهم"
    assert document["caption_preview"] == "مرور نکات مهم"
    assert document["file_size"] == 2048
    assert document["mime_type"] == "application/pdf"
    assert document["media_type"] == "Document"
    assert document["posted_at"] == "2026-11-07T10:00:00+00:00"


def test_catalog_document_hash_is_stable_and_tracks_display_changes():
    assert search_document_hash({"title": "کتاب", "id": 4}) == search_document_hash(
        {"id": 4, "title": "کتاب"}
    )
    assert search_document_hash({"title": "کتاب"}) != search_document_hash(
        {"title": "کتاب تازه"}
    )


def test_catalog_search_fixture_has_at_least_50_valid_scenarios():
    fixture_path = Path(__file__).with_name("catalog_search_cases.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    document_ids = {document["message_id"] for document in fixture["documents"]}
    scenarios = fixture["scenarios"]

    assert len(scenarios) >= 50
    assert all(
        scenario["expected_ids"]
        and set(scenario["expected_ids"]).issubset(document_ids)
        for scenario in scenarios
    )
    queries = {scenario["query"] for scenario in scenarios}
    assert "تحلیل قدرت دنیا" in queries
    assert "تحلیل دنیا قدرت" in queries
    assert "رمان" in queries
    assert "pdf" in queries
    assert "جریان سیال ذهن" in queries
    assert "حسابدارز" in queries
    assert "يادگيري ماشين" in queries
    assert "کتابها" in queries
    assert "the art of war" in queries
    assert "python برنامه نویسی" in queries
