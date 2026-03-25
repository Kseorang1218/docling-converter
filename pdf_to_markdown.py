import argparse
import logging
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

_log = logging.getLogger(__name__)


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
    pipeline_options.images_scale = 2.0
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

    # 2. Markdown 저장
    md_path = output_dir / f"{doc_filename}.md"
    with md_path.open("w", encoding="utf-8") as fp:
        fp.write(conv_result.document.export_to_markdown())
    _log.info(f"Markdown saved: {md_path}")


if __name__ == "__main__":
    main()
