import re
import unicodedata
from pathlib import Path

INVALID_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
MAX_FILENAME_BYTES = 150
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def sanitize_title(text: str) -> str | None:
    """Return a portable, byte-length-bounded filename component."""
    title = unicodedata.normalize("NFC", text.strip())
    title = INVALID_FILENAME_CHARS_RE.sub("_", title)
    title = re.sub(r"\s+", " ", title)
    title = _truncate_utf8(title, MAX_FILENAME_BYTES).rstrip(" .")
    if not title:
        return None
    if title.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        title = f"_{title}"
    return title


def document_name(title: str | None, input_path: Path) -> str:
    return sanitize_title(title or "") or sanitize_title(input_path.stem) or "document"

