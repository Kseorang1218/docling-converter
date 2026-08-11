# Doclings

[Docling](https://github.com/DS4SD/docling) 또는 [MinerU](https://github.com/opendatalab/MinerU) 기반 PDF to Markdown 변환기. OCR을 활용하여 PDF에서 텍스트, 표, 이미지를 추출합니다.

## 주요 기능

- OCR 기반 PDF to Markdown 변환
- 표 구조 인식
- 수식(formula) 인식
- 코드 블록(code) 인식
- 이미지 추출
- 페이지 하단 주석 및 저자 제공 링크 보존
- 다국어 OCR 지원
- GPU 자동 감지 및 가속
- `--tool` 옵션으로 Docling / MinerU 변환 엔진 선택

## 설치

### Docling (기본 엔진)

```bash
python3 -m venv doc
doc/bin/pip install -r requirements-docling.txt
```

### MinerU (`--tool mineru`용, 선택)

Docling과 요구하는 torch 버전이 달라(2.11 vs 2.13) 별도 가상환경을 사용합니다:

```bash
python3 -m venv venv-mineru
venv-mineru/bin/pip install -r requirements-mineru.txt
```

`requirements-*.txt`는 각 가상환경에서 사용하는 전체 의존성 버전을 고정한 파일입니다. 두 파일은 서로 다른 torch 버전을 요구하므로 하나의 가상환경에 함께 설치하면 안 됩니다.

## 사용법

```bash
doc/bin/python pdf_to_markdown.py <입력PDF> [-o 출력경로] [-l 언어 ...] [--tool docling|mineru] [--overwrite]
```

`doc` 가상환경을 활성화한 상태라면 `doc/bin/python` 대신 `python`을 사용해도 됩니다. MinerU를 선택해도 래퍼 스크립트 자체는 `doc` 환경에서 실행하며, 실제 MinerU 변환만 `venv-mineru/bin/mineru` 프로세스로 분리됩니다.

### 인자

| 인자 | 설명 | 기본값 |
|---|---|---|
| `input` | 변환할 PDF 파일 경로 | (필수) |
| `-o`, `--output` | 출력 기본 디렉토리 | `results` |
| `-l`, `--lang` | OCR 언어 (`--tool docling` 전용, mineru에서는 무시됨) | `en` |
| `--tool` | 변환 엔진 (`docling` 또는 `mineru`) | `docling` |
| `--overwrite` | 입력 식별자가 다른 기존 제목 폴더도 명시적으로 교체 | 사용 안 함 |

### 예시

```bash
# 영어 PDF (기본값, docling 사용)
doc/bin/python pdf_to_markdown.py document.pdf

# 한국어 PDF
doc/bin/python pdf_to_markdown.py document.pdf -l ko

# 한국어 + 영어 혼합 PDF
doc/bin/python pdf_to_markdown.py document.pdf -l ko en

# 출력 경로 지정
doc/bin/python pdf_to_markdown.py document.pdf -o output -l ko

# MinerU로 변환 (venv-mineru 설치 필요)
doc/bin/python pdf_to_markdown.py document.pdf --tool mineru
```

## 출력 구조

결과물은 `results/<파일명>/` 하위에 저장됩니다. 파일명은 문서에서 인식한 논문 제목이며, 인식하지 못한 경우 원본 PDF 파일명을 사용합니다.

```
results/
  document/
    .doclings.json      # 입력 SHA-256, 변환 엔진 등 결과 식별 정보
    document.md
    document_img_1.png  # Docling: Markdown에서 상대경로로 참조
    document_img_2.png
    ...
```

MinerU 이미지는 기존 MinerU 출력 형식대로 `images/` 하위에 저장되고 Markdown에서 상대경로로 참조됩니다.

모든 산출물은 출력 루트의 임시 폴더에서 먼저 완성된 뒤 최종 폴더로 교체됩니다. 입력 SHA-256과 인식 제목이 모두 같은 문서를 다시 변환하면 기존 결과를 갱신합니다. 제목은 같지만 입력이 다른 문서이거나, 식별 정보가 없는 과거 결과가 있으면 `document--12ab34cd/`처럼 해시 접미사가 붙은 별도 폴더에 저장하여 기존 결과를 보존합니다. 의도적으로 제목 폴더를 교체하려면 `--overwrite`를 사용합니다.

변환 실패, 입력 파일 부재, MinerU 미설치 시 프로세스는 종료 코드 `1`을 반환합니다.

## 테스트

외부 OCR 모델을 실행하지 않는 단위 테스트는 다음과 같이 실행합니다.

```bash
doc/bin/python -B -m unittest discover -s tests -v
```
