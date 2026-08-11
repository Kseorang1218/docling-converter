import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .errors import ConversionError
from .naming import document_name, sanitize_title

_log = logging.getLogger(__name__)

DEFAULT_MINERU_BIN = (
    Path(__file__).resolve().parent.parent / "venv-mineru" / "bin" / "mineru"
)
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
TITLE_SEARCH_LINES = 10
URL_RE = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)


def markdown_title(content: str) -> str | None:
    """Find the first markdown heading near the top of the document.

    Some journals prefix the title with a short section badge (e.g. "FOCUS")
    that MinerU emits as plain text on its own line, so the real heading can
    be a few lines down rather than on the very first line.
    """
    stripped = content.lstrip()
    if not stripped:
        return None
    for line in stripped.splitlines()[:TITLE_SEARCH_LINES]:
        match = MARKDOWN_HEADING_RE.match(line)
        if match:
            return sanitize_title(match.group(1))
    return None


def append_page_footnotes(content: str, content_list: object) -> tuple[str, int]:
    """Append page footnotes that MinerU recognized but omitted from Markdown."""
    if not isinstance(content_list, list):
        return content, 0

    normalized_content = " ".join(content.split())
    seen: set[str] = set()
    notes: list[tuple[int | None, str]] = []
    for item in content_list:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        text = item.get("text")
        if not isinstance(text, str):
            continue

        note = " ".join(text.split())
        if not note:
            continue
        # MinerU always discards page_footnote blocks. It also discards footer
        # blocks, so recover those when they contain an author-provided link.
        if item_type != "page_footnote" and not (
            item_type == "footer" and URL_RE.search(note)
        ):
            continue
        if note in normalized_content or note in seen:
            continue

        seen.add(note)
        page_idx = item.get("page_idx")
        page_no = page_idx + 1 if isinstance(page_idx, int) else None
        notes.append((page_no, note))

    if not notes:
        return content, 0

    lines = ["## Page footnotes", ""]
    for page_no, note in notes:
        prefix = f"- Page {page_no}: " if page_no is not None else "- "
        lines.append(prefix + note)
    updated = content.rstrip() + "\n\n" + "\n".join(lines) + "\n"
    return updated, len(notes)


def convert_with_mineru(
    input_path: Path,
    stage: Path,
    mineru_bin: Path = DEFAULT_MINERU_BIN,
) -> str:
    if not mineru_bin.is_file():
        raise ConversionError(
            f"MinerU 실행 파일을 찾을 수 없습니다: {mineru_bin}\n"
            f"  python3 -m venv {mineru_bin.parent.parent}\n"
            f'  {mineru_bin.parent}/pip install "mineru[core]"'
        )

    _log.info("Starting conversion with MinerU...")
    start_time = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="mineru-") as temporary:
        temporary_path = Path(temporary)
        try:
            subprocess.run(
                [str(mineru_bin), "-p", str(input_path), "-o", str(temporary_path)],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ConversionError(f"MinerU conversion failed: {exc}") from exc

        markdown_candidates = sorted(temporary_path.rglob("*.md"))
        if not markdown_candidates:
            raise ConversionError("MinerU did not produce a markdown file.")
        if len(markdown_candidates) > 1:
            raise ConversionError(
                f"MinerU produced multiple markdown files ({len(markdown_candidates)})."
            )

        source_markdown = markdown_candidates[0]
        content = source_markdown.read_text(encoding="utf-8")
        content_list_path = source_markdown.with_name(
            f"{source_markdown.stem}_content_list.json"
        )
        if content_list_path.is_file():
            try:
                content_list = json.loads(content_list_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                _log.warning("Could not read MinerU content list: %s", exc)
            else:
                content, footnote_count = append_page_footnotes(content, content_list)
                _log.info("Page footnotes recovered: %d", footnote_count)
        else:
            _log.warning(
                "MinerU content list not found; page footnotes cannot be recovered."
            )
        name = document_name(markdown_title(content), input_path)

        images_source = source_markdown.parent / "images"
        image_count = 0
        if images_source.is_dir():
            shutil.copytree(images_source, stage / "images")
            image_count = sum(
                1 for path in (stage / "images").rglob("*") if path.is_file()
            )
        _log.info("Total images extracted: %d", image_count)

        (stage / f"{name}.md").write_text(
            content.replace("\x00", ""), encoding="utf-8"
        )
        _log.info("Conversion done in %.2fs", time.monotonic() - start_time)
        return name
