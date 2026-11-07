from BOOKzMA.services.catalog_text import is_generic_search_query


def test_catalog_rejects_generic_broad_queries():
    assert is_generic_search_query("کتاب") is True
    assert is_generic_search_query("رمان") is True
    assert is_generic_search_query("مرگ فروشنده") is False
    assert is_generic_search_query("مرد") is False
    assert is_generic_search_query("pdf") is True
