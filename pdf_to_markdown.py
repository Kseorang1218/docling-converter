import argparse
import logging
import time
from pathlib import Path

import torch  # PyTorch 임포트 추가

# TensorFloat32 관련 경고를 해결하기 위해 정밀도 설정 변경
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

    parser = argparse.ArgumentParser(description="PDF를 마크다운으로 변환합니다.")
    parser.add_argument("input", type=Path, help="변환할 PDF 파일 경로")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("results"), help="출력 디렉토리 (기본값: results)"
    )
    args = parser.parse_args()

    input_doc_path: Path = args.input.resolve()
    output_dir: Path = args.output

    if not input_doc_path.exists():
        _log.error(f"파일을 찾을 수 없습니다: {input_doc_path}")
        return

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.generate_picture_images = True
    pipeline_options.do_picture_classification = True
    pipeline_options.images_scale = 2.0
    pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True)
    pipeline_options.ocr_options.lang = ["ko"]
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

    _log.info("문서 변환 시작 (이미지 추출 포함)...")
    start_time = time.time()
    try:
        conv_result = doc_converter.convert(input_doc_path)
    except Exception as e:
        _log.error(f"변환 실패: {e}")
        return
    _log.info(f"변환 완료: {time.time() - start_time:.2f}초 소요")

    output_dir.mkdir(parents=True, exist_ok=True)
    doc_filename = conv_result.input.file.stem

    # 1. 이미지 먼저 저장
    saved_count = 0
    for i, picture in enumerate(conv_result.document.pictures):
        image_save_path = output_dir / f"{doc_filename}_img_{i + 1}.png"
        if picture.image and picture.image.pil_image:
            picture.image.pil_image.save(image_save_path, "PNG")
            _log.info(f"이미지 저장 성공: {image_save_path}")
            saved_count += 1
        else:
            _log.warning(f"{i + 1}번째 그림 요소를 찾았으나 이미지 데이터가 없습니다.")

    _log.info(f"최종 추출된 이미지 개수: {saved_count}")

    # 2. Markdown 저장
    md_path = output_dir / f"{doc_filename}.md"
    with md_path.open("w", encoding="utf-8") as fp:
        fp.write(conv_result.document.export_to_markdown())
    _log.info(f"마크다운 저장 완료: {md_path}")


if __name__ == "__main__":
    main()
