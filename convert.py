import logging
import time
from pathlib import Path

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend 
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
# 그림 아이템 식별을 위한 임포트
from docling_core.types.doc import PictureItem

_log = logging.getLogger(__name__)

def main():
    logging.basicConfig(level=logging.INFO)

    # 경로 설정 (실제 파일이 있는지 확인 로직 추가)
    data_folder = Path(__file__).parent / "../Downloads"
    input_doc_path = data_folder / "9f0ca2eb-77fb-42af-9f37-57c50e78015e_연구_주제_구체화.pdf"
    
    if not input_doc_path.exists():
        _log.error(f"파일을 찾을 수 없습니다: {input_doc_path}")
        return

    # [수정] 파이프라인 옵션: 이미지 추출을 위해 필수 설정 추가
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    
    # 그림 분류 및 추출 활성화
    pipeline_options.generate_picture_images = True
    pipeline_options.do_picture_classification = True  # 그림인지 아닌지 분류 활성화
    pipeline_options.images_scale = 2.0  # [중요] 이미지를 렌더링할 해상도 비율 (2.0 = 300DPI 수준)

    pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True)
    pipeline_options.ocr_options.lang = ["ko"]
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=4, device=AcceleratorDevice.AUTO
    )

    doc_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options, 
                backend=PyPdfiumDocumentBackend 
            )
        }
    )

    _log.info("문서 변환 시작 (이미지 추출 포함)...")
    start_time = time.time()
    conv_result = doc_converter.convert(input_doc_path)
    end_time = time.time() - start_time
    _log.info(f"변환 완료: {end_time:.2f}초 소요")

    ## 결과 저장
    output_dir = Path("results")
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_filename = conv_result.input.file.stem

    # 1. Markdown 저장
    md_path = output_dir / f"{doc_filename}.md"
    with md_path.open("w", encoding="utf-8") as fp:
        fp.write(conv_result.document.export_to_markdown())
    _log.info(f"마크다운 저장 완료: {md_path}")

    # 2. 이미지 추출 및 물리적 파일 저장
    image_counter = 0
    # iterate_items 대신 document.pictures를 직접 순회하는 것이 더 확실할 수 있습니다.
    for i, picture in enumerate(conv_result.document.pictures):
        image_counter += 1
        image_filename = f"{doc_filename}_img_{image_counter}.png"
        image_save_path = output_dir / image_filename
        
        # [중요] 렌더링된 이미지가 있는지 확인 후 저장
        if picture.image and picture.image.pil_image:
            picture.image.pil_image.save(image_save_path, "PNG")
            _log.info(f"이미지 저장 성공: {image_save_path}")
        else:
            _log.warning(f"{image_counter}번째 그림 요소를 찾았으나 이미지 데이터가 없습니다.")

    _log.info(f"최종 추출된 이미지 개수: {image_counter}")

if __name__ == "__main__":
    main()