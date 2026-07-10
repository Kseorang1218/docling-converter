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
from docling_core.types.doc import FormulaItem

_log = logging.getLogger(__name__)

# CodeFormula 모델이 복잡한 다줄 수식을 인식하지 못하면 반복 억제 장치가 없어
# "&"만 수백~수천 번 반복하며 폭주하는 경우가 있다. 정상/경미하게 깨진 수식은
# 연속 & 이 몇 개를 넘지 않으므로, 이 임계값으로 진짜 폭주 구간만 골라 잘라낸다.
RUNAWAY_AMP_RE = re.compile(r"(?:&\s*){8,}")
MAX_FORMULA_LEN = 1500


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

    doc_filename = conv_result.input.file.stem
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
