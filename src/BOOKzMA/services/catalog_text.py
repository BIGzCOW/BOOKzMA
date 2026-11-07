import re
import unicodedata


CAPTION_SEARCH_LIMIT = 4000
CAPTION_PREVIEW_LIMIT = 220
SEARCH_TEXT_LIMIT = 6000
CHANNEL_HANDLE_RE = re.compile(r"@[A-Za-z0-9_]{5,32}")
GENERIC_SEARCH_WORDS = {
    "کتاب",
    "کتاب‌ها",
    "کتابها",
    "رمان",
    "رمان‌ها",
    "رمانها",
    "داستان",
    "داستان‌ها",
    "داستانها",
    "نویسنده",
    "نویسندگان",
    "پی‌دی‌اف",
    "pdf",
    "epub",
    "مقاله",
    "فایل",
    "book",
    "books",
}


def is_generic_search_query(value: str) -> bool:
    normalized = normalize_catalog_text(value)
    if not normalized:
        return True
    tokens = [token for token in normalized.split() if token]
    if len(tokens) == 1:
        token = tokens[0]
        return len(token) < 3 or token in GENERIC_SEARCH_WORDS
    if len(tokens) <= 2:
        return len(" ".join(tokens)) < 5
    return False


def strip_channel_handles(value: str | None) -> str:
    if value is None:
        return ""
    cleaned = re.sub(CHANNEL_HANDLE_RE, "", value)
    return re.sub(r"\s{2,}", " ", cleaned).strip(" ._-\n\t")


def normalize_catalog_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(
        str.maketrans(
            {
                "ي": "ی",
                "ى": "ی",
                "ك": "ک",
                "ۀ": "ه",
                "ة": "ه",
                "ؤ": "و",
                "أ": "ا",
                "إ": "ا",
                "ٱ": "ا",
                "ـ": "",
                "\u200c": " ",
            }
        )
    )
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"\s+", " ", normalized).strip().lower()


def clean_caption(value: str | None, channel_username: str) -> tuple[str, str, str]:
    if not value:
        return "", "", ""
    username = re.escape(channel_username.lstrip("@"))
    signature = re.compile(
        rf"(?i)(?<![\w])(?:@|https?://)?(?:t\.me/)?{username}(?![\w])"
    )
    display = re.sub(r"\s+", " ", signature.sub(" ", value)).strip()
    preview = display[:CAPTION_PREVIEW_LIMIT]
    if len(display) > CAPTION_PREVIEW_LIMIT:
        preview = preview.rsplit(" ", 1)[0] or preview
        preview += "…"
    searchable = normalize_catalog_text(display)[:CAPTION_SEARCH_LIMIT]
    return display, preview, searchable