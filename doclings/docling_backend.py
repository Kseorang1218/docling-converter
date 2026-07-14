import logging
import re
import time
from pathlib import Path

from .errors import ConversionError
from .naming import document_name

_log = logging.getLogger(__name__)

RUNAWAY_AMP_RE = re.compile(r"(?:&\s*){8,}")


def document_title(document) -> str | None:
    """Find the first plausible paper title in a Docling document."""
    from docling_core.types.doc import SectionHeaderItem, TitleItem

    same_page_headers: dict[int, list[str]] = {}
    for item in document.texts:
        if getattr(item, "label", None) == "page_header" and item.prov:
            same_page_headers.setdefault(item.prov[0].page_no, []).append(
                item.text.strip()
            )

    title_item = None
    badge_pending = False
    for item in document.texts:
        text = item.text.strip()

        if badge_pending:
            badge_pending = False
            if text and len(text) > 15:
                title_item = item
                break

        if not isinstance(item, (TitleItem, SectionHeaderItem)) or not text:
            continue
        if len(text) <= 20 and text.isascii() and text.isupper():
            badge_pending = True
            continue
        page_no = item.prov[0].page_no if item.prov else None
        if any(text in header for header in same_page_headers.get(page_no, [])):
            continue
        title_item = item
        break

    return title_item.text if title_item is not None else None


def broken_formula_span(text: str) -> tuple[int, int] | None:
    match = RUNAWAY_AMP_RE.search(text)
    if match:
        return match.span()
    return None


def _save_picture_images(document, stage: Path, name: str) -> int:
    saved_count = 0
    for index, picture in enumerate(document.pictures, start=1):
        image = picture.image
        if image and image.pil_image:
            image_name = f"{name}_img_{index}.png"
            image.pil_image.save(stage / image_name, "PNG")
            # REFERENCED Markdown mode serializes this relative URI.
            image.uri = Path(image_name)
            saved_count += 1
        else:
            _log.warning("Picture element %d found but no image data available.", index)
    return saved_count


def _collapse_broken_formulas(document, stage: Path, name: str) -> int:
    from docling_core.types.doc import FormulaItem

    broken_count = 0
    for item in document.texts:
        if not isinstance(item, FormulaItem):
            continue
        span = broken_formula_span(item.text)
        if span is None:
            continue

        start, end = span
        broken_count += 1
        note = "…[인식 실패로 일부 생략됨]…"
        crop = item.get_image(document)
        if crop is not None:
            image_name = f"{name}_formula_broken_{broken_count}.png"
            crop.save(stage / image_name, "PNG")
            note = f"…[인식 실패로 일부 생략됨 — 원본 이미지: {image_name}]…"
        item.text = item.text[:start] + note + item.text[end:]
    return broken_count


def convert_with_docling(input_path: Path, stage: Path, lang: list[str]) -> str:
    import torch
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc import ImageRefMode

    torch.set_float32_matmul_precision("high")

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.generate_picture_images = True
    pipeline_options.do_picture_classification = True
    pipeline_options.do_formula_enrichment = True
    pipeline_options.do_code_enrichment = True
    pipeline_options.images_scale = 2.0
    pipeline_options.generate_page_images = True
    pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True)
    pipeline_options.ocr_options.lang = lang
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=4, device=AcceleratorDevice.AUTO
    )

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=PyPdfiumDocumentBackend,
            )
        }
    )

    _log.info("Starting conversion with Docling (lang=%s)...", lang)
    start_time = time.monotonic()
    try:
        result = converter.convert(input_path)
    except Exception as exc:
        raise ConversionError(f"Docling conversion failed: {exc}") from exc
    _log.info("Conversion done in %.2fs", time.monotonic() - start_time)

    name = document_name(document_title(result.document), input_path)
    saved_count = _save_picture_images(result.document, stage, name)
    _log.info("Total images extracted: %d", saved_count)

    broken_count = _collapse_broken_formulas(result.document, stage, name)
    if broken_count:
        _log.warning("Collapsed runaway repetition in %d formula(s).", broken_count)

    markdown = result.document.export_to_markdown(image_mode=ImageRefMode.REFERENCED)
    (stage / f"{name}.md").write_text(markdown, encoding="utf-8")
    return name
