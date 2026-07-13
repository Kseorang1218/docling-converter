import argparse
import logging
import re
import time
from pathlib import Path

import torch

# Use high precision for TF32 matmul to suppress warnings
torch.set_float32_matmul_precision('high')

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import FormulaItem, SectionHeaderItem, TitleItem

_log = logging.getLogger(__name__)

# CodeFormula 모델이 복잡한 다줄 수식을 인식하지 못하면 반복 억제 장치가 없어
# "&"만 수백~수천 번 반복하며 폭주하는 경우가 있다. 정상/경미하게 깨진 수식은
# 연속 & 이 몇 개를 넘지 않으므로, 이 임계값으로 진짜 폭주 구간만 골라 잘라낸다.
RUNAWAY_AMP_RE = re.compile(r"(?:&\s*){8,}")
MAX_FORMULA_LEN = 1500

INVALID_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|]')
MAX_FILENAME_LEN = 150


def _document_title(document) -> str | None:
    """문서에서 인식된 논문 제목을 찾아 파일명으로 쓸 수 있게 정리한다.

    Docling 레이아웃 모델이 논문 제목을 TitleItem이 아니라 최상위
    SectionHeaderItem으로 분류하는 경우가 많아(예: arXiv 2단 레이아웃 논문),
    문서에서 가장 먼저 등장하는 제목류(TitleItem 또는 SectionHeaderItem)
    아이템을 제목 후보로 본다. 다만 저널명이 1페이지 상단(page_header)에
    함께 인쇄되는 경우 그 저널명이 제목류로 잘못 분류되기도 하므로, 같은
    페이지의 page_header와 겹치는 후보는 건너뛴다. (2페이지 이후 헤더에는
    본문 제목 자체가 반복 인쇄되는 경우가 많아 페이지를 한정한다.)
    """
    same_page_headers: dict[int, list[str]] = {}
    for t in document.texts:
        if getattr(t, "label", None) == "page_header" and t.prov:
            same_page_headers.setdefault(t.prov[0].page_no, []).append(t.text.strip())

    title_item = None
    badge_pending = False
    for t in document.texts:
        text = t.text.strip()

        # "PAPER" 같은 배지 바로 다음에 오는 텍스트는, 그것이 헤딩으로
        # 인식되지 않았더라도(예: 일반 TextItem) 실제 제목일 가능성이 높다.
        if badge_pending:
            badge_pending = False
            if text and len(text) > 15:
                title_item = t
                break

        if not isinstance(t, (TitleItem, SectionHeaderItem)) or not text:
            continue
        # 일부 저널 템플릿은 "PAPER", "REVIEW ARTICLE" 같은 짧은 전체대문자
        # 배지를 실제 제목 바로 앞에 별도 헤딩으로 넣으므로 건너뛴다.
        if len(text) <= 20 and text.isascii() and text.isupper():
            badge_pending = True
            continue
        page_no = t.prov[0].page_no if t.prov else None
        page_headers = same_page_headers.get(page_no, [])
        if any(text in ph for ph in page_headers):
            continue
        title_item = t
        break

    if title_item is None:
        return None

    title = INVALID_FILENAME_CHARS_RE.sub("_", title_item.text.strip())
    title = re.sub(r"\s+", " ", title)
    return title[:MAX_FILENAME_LEN].rstrip(" .") or None


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Convert PDF to Markdown.")
    parser.add_argument("input", type=Path, help="Path to the PDF file to convert")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("results"), help="Output directory (default: results)"
    )
    parser.add_argument(
        "-l", "--lang", nargs="+", default=["en"], help="OCR language(s) (default: en). e.g. -l ko en"
    )
    args = parser.parse_args()

    input_doc_path: Path = args.input.resolve()
    output_dir: Path = args.output

    if not input_doc_path.exists():
        _log.error(f"File not found: {input_doc_path}")
        return

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.generate_picture_images = True
    pipeline_options.do_picture_classification = True
    pipeline_options.do_formula_enrichment = True
    pipeline_options.do_code_enrichment = True
    pipeline_options.images_scale = 2.0
    pipeline_options.generate_page_images = True  # 수식 인식 실패 시 원본 이미지를 잘라내기 위해 필요
    pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True)
    pipeline_options.ocr_options.lang = args.lang
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=4, device=AcceleratorDevice.AUTO
    )

    doc_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=PyPdfiumDocumentBackend,
            )
        }
    )

    _log.info(f"Starting conversion (lang={args.lang})...")
    start_time = time.time()
    try:
        conv_result = doc_converter.convert(input_doc_path)
    except Exception as e:
        _log.error(f"Conversion failed: {e}")
        return
    _log.info(f"Conversion done in {time.time() - start_time:.2f}s")

    doc_filename = _document_title(conv_result.document) or conv_result.input.file.stem
    output_dir = args.output / doc_filename
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save images
    saved_count = 0
    for i, picture in enumerate(conv_result.document.pictures):
        image_save_path = output_dir / f"{doc_filename}_img_{i + 1}.png"
        if picture.image and picture.image.pil_image:
            picture.image.pil_image.save(image_save_path, "PNG")
            _log.info(f"Image saved: {image_save_path}")
            saved_count += 1
        else:
            _log.warning(f"Picture element {i + 1} found but no image data available.")

    _log.info(f"Total images extracted: {saved_count}")

    # 2. 폭주한 "&" 반복 구간만 잘라내고 나머지 텍스트는 보존
    #    (일부 깨지더라도 텍스트로 남겨야 다른 AI에게 넘겨 활용할 수 있으므로,
    #     통째로 이미지로 바꾸지 않고 반복 구간만 최소한으로 제거한다)
    broken_count = 0
    for item in conv_result.document.texts:
        if not isinstance(item, FormulaItem):
            continue

        match = RUNAWAY_AMP_RE.search(item.text)
        if match:
            start, end = match.span()
        elif len(item.text) > MAX_FORMULA_LEN:
            start, end = 300, len(item.text)
        else:
            continue

        broken_count += 1
        note = "…[인식 실패로 일부 생략됨]…"
        crop = item.get_image(conv_result.document)
        if crop is not None:
            img_name = f"{doc_filename}_formula_broken_{broken_count}.png"
            crop.save(output_dir / img_name, "PNG")
            note = f"…[인식 실패로 일부 생략됨 — 원본 이미지: {img_name}]…"
        item.text = item.text[:start] + note + item.text[end:]

    if broken_count:
        _log.warning(f"Collapsed runaway repetition in {broken_count} formula(s).")

    # 3. Markdown 저장
    md_path = output_dir / f"{doc_filename}.md"
    with md_path.open("w", encoding="utf-8") as fp:
        fp.write(conv_result.document.export_to_markdown())
    _log.info(f"Markdown saved: {md_path}")


if __name__ == "__main__":
    main()
