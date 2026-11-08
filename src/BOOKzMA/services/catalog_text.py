import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping


CAPTION_SEARCH_LIMIT = 4000
CAPTION_PREVIEW_LIMIT = 220
SEARCH_TEXT_LIMIT = 6000
CHANNEL_HANDLE_RE = re.compile(r"@[A-Za-z0-9_]{5,32}")
PERSIAN_PLURAL_SUFFIX_RE = re.compile(r"(?<=[\u0600-\u06ff])ها\b")
PERSIAN_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)
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
    normalized = normalized.translate(PERSIAN_DIGIT_TRANSLATION)
    normalized = PERSIAN_PLURAL_SUFFIX_RE.sub(" ها", normalized)
    return re.sub(r"\s+", " ", normalized).strip().lower()


def build_search_document(
    *,
    message_id: int,
    file_name: str | None,
    caption_preview: str | None,
    caption_search: str,
    file_size: int | None,
    mime_type: str | None,
    media_type: str | None,
    posted_at: str | None,
) -> dict[str, int | str | None]:
    display_file_name = strip_channel_handles(file_name) or None
    title_source = display_file_name or ""
    title_source = re.split(r"[/\\]", title_source)[-1]
    if "." in title_source and not title_source.startswith("."):
        title_source = title_source.rsplit(".", 1)[0]
    title = normalize_catalog_text(re.sub(r"[_\-.]+", " ", title_source))

    return {
        "id": message_id,
        "title": title,
        "file_name": normalize_catalog_text(display_file_name or ""),
        "display_file_name": display_file_name,
        "caption": normalize_catalog_text(caption_search),
        "caption_preview": caption_preview,
        "file_size": file_size,
        "mime_type": mime_type,
        "media_type": media_type,
        "posted_at": posted_at,
    }


def search_document_hash(document: Mapping[str, object]) -> str:
    serialized = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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