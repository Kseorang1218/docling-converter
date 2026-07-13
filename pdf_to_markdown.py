import argparse
import logging
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

_log = logging.getLogger(__name__)

# CodeFormula 모델이 복잡한 다줄 수식을 인식하지 못하면 반복 억제 장치가 없어
# "&"만 수백~수천 번 반복하며 폭주하는 경우가 있다. 정상/경미하게 깨진 수식은
# 연속 & 이 몇 개를 넘지 않으므로, 이 임계값으로 진짜 폭주 구간만 골라 잘라낸다.
RUNAWAY_AMP_RE = re.compile(r"(?:&\s*){8,}")
MAX_FORMULA_LEN = 1500

INVALID_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|]')
MAX_FILENAME_LEN = 150

# MinerU는 docling과 torch 요구 버전이 달라 별도 venv를 사용한다
# (프로젝트 루트에 `python3 -m venv venv-mineru && venv-mineru/bin/pip install "mineru[core]"`로 준비).
MINERU_BIN = Path(__file__).resolve().parent / "venv-mineru" / "bin" / "mineru"


def _sanitize_title(text: str) -> str | None:
    title = INVALID_FILENAME_CHARS_RE.sub("_", text.strip())
    title = re.sub(r"\s+", " ", title)
    return title[:MAX_FILENAME_LEN].rstrip(" .") or None


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
    from docling_core.types.doc import SectionHeaderItem, TitleItem

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

    return _sanitize_title(title_item.text)


def convert_with_docling(input_doc_path: Path, output_dir: Path, lang: list[str]) -> None:
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
    pipeline_options.ocr_options.lang = lang
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

    _log.info(f"Starting conversion with Docling (lang={lang})...")
    start_time = time.time()
    try:
        conv_result = doc_converter.convert(input_doc_path)
    except Exception as e:
        _log.error(f"Conversion failed: {e}")
        return
    _log.info(f"Conversion done in {time.time() - start_time:.2f}s")

    doc_filename = _document_title(conv_result.document) or conv_result.input.file.stem
    doc_output_dir = output_dir / doc_filename
    # 같은 문서를 다른 --tool로 재변환했을 때 이전 도구가 남긴 파일이 섞이지
    # 않도록, 매 실행마다 결과 폴더를 비우고 새로 만든다.
    if doc_output_dir.exists():
        shutil.rmtree(doc_output_dir)
    doc_output_dir.mkdir(parents=True)

    # 1. Save images
    saved_count = 0
    for i, picture in enumerate(conv_result.document.pictures):
        image_save_path = doc_output_dir / f"{doc_filename}_img_{i + 1}.png"
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
            crop.save(doc_output_dir / img_name, "PNG")
            note = f"…[인식 실패로 일부 생략됨 — 원본 이미지: {img_name}]…"
        item.text = item.text[:start] + note + item.text[end:]

    if broken_count:
        _log.warning(f"Collapsed runaway repetition in {broken_count} formula(s).")

    # 3. Markdown 저장
    md_path = doc_output_dir / f"{doc_filename}.md"
    with md_path.open("w", encoding="utf-8") as fp:
        fp.write(conv_result.document.export_to_markdown())
    _log.info(f"Markdown saved: {md_path}")


def convert_with_mineru(input_doc_path: Path, output_dir: Path) -> None:
    if not MINERU_BIN.exists():
        _log.error(
            f"MinerU venv를 찾을 수 없습니다: {MINERU_BIN}\n"
            f"  python3 -m venv {MINERU_BIN.parent.parent}\n"
            f'  {MINERU_BIN.parent}/pip install "mineru[core]"\n'
            f"먼저 위 명령으로 설치해주세요."
        )
        return

    _log.info("Starting conversion with MinerU...")
    start_time = time.time()
    with tempfile.TemporaryDirectory(prefix="mineru_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        result = subprocess.run(
            [str(MINERU_BIN), "-p", str(input_doc_path), "-o", str(tmp_path)]
        )
        if result.returncode != 0:
            _log.error(f"MinerU conversion failed (exit code {result.returncode}).")
            return

        md_candidates = sorted(tmp_path.rglob("*.md"))
        if not md_candidates:
            _log.error("MinerU did not produce a markdown file.")
            return
        md_path = md_candidates[0]
        _log.info(f"Conversion done in {time.time() - start_time:.2f}s")

        first_line = ""
        content = md_path.read_text(encoding="utf-8")
        if content.strip():
            first_line = content.lstrip().splitlines()[0]

        title = _sanitize_title(first_line.lstrip("#").strip()) if first_line.startswith("#") else None
        doc_filename = title or input_doc_path.stem

        doc_output_dir = output_dir / doc_filename
        # 같은 문서를 다른 --tool로 재변환했을 때 이전 도구가 남긴 파일이 섞이지
        # 않도록, 매 실행마다 결과 폴더를 비우고 새로 만든다.
        if doc_output_dir.exists():
            shutil.rmtree(doc_output_dir)
        doc_output_dir.mkdir(parents=True)

        images_src = md_path.parent / "images"
        image_count = 0
        if images_src.is_dir():
            shutil.copytree(images_src, doc_output_dir / "images")
            image_count = sum(1 for _ in (doc_output_dir / "images").iterdir())
        _log.info(f"Total images extracted: {image_count}")

        final_md_path = doc_output_dir / f"{doc_filename}.md"
        shutil.copyfile(md_path, final_md_path)
        _log.info(f"Markdown saved: {final_md_path}")


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Convert PDF to Markdown.")
    parser.add_argument("input", type=Path, help="Path to the PDF file to convert")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("results"), help="Output directory (default: results)"
    )
    parser.add_argument(
        "-l", "--lang", nargs="+", default=["en"],
        help="OCR language(s) for --tool docling (default: en). e.g. -l ko en. Ignored when --tool mineru.",
    )
    parser.add_argument(
        "--tool", choices=["docling", "mineru"], default="docling",
        help="Conversion backend to use (default: docling)",
    )
    args = parser.parse_args()

    input_doc_path: Path = args.input.resolve()

    if not input_doc_path.exists():
        _log.error(f"File not found: {input_doc_path}")
        return

    if args.tool == "mineru" and args.lang != ["en"]:
        _log.warning("--lang is ignored when --tool mineru is used.")

    if args.tool == "docling":
        convert_with_docling(input_doc_path, args.output, args.lang)
    else:
        convert_with_mineru(input_doc_path, args.output)


if __name__ == "__main__":
    main()
