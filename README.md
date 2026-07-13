# Doclings

[Docling](https://github.com/DS4SD/docling) 또는 [MinerU](https://github.com/opendatalab/MinerU) 기반 PDF to Markdown 변환기. OCR을 활용하여 PDF에서 텍스트, 표, 이미지를 추출합니다.

## 주요 기능

- OCR 기반 PDF to Markdown 변환
- 표 구조 인식
- 수식(formula) 인식
- 코드 블록(code) 인식
- 이미지 추출
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

`requirements-*.txt`는 실제로 테스트한 전체 의존성 버전을 고정한 lock 파일입니다. 버전 고정 없이 최신 버전으로 설치하려면 `pip install docling torch` / `pip install "mineru[core]"`를 대신 사용하세요.

## 사용법

```bash
python pdf_to_markdown.py <입력PDF> [-o 출력경로] [-l 언어 ...] [--tool docling|mineru]
```

### 인자

| 인자 | 설명 | 기본값 |
|---|---|---|
| `input` | 변환할 PDF 파일 경로 | (필수) |
| `-o`, `--output` | 출력 기본 디렉토리 | `results` |
| `-l`, `--lang` | OCR 언어 (`--tool docling` 전용, mineru에서는 무시됨) | `en` |
| `--tool` | 변환 엔진 (`docling` 또는 `mineru`) | `docling` |

### 예시

```bash
# 영어 PDF (기본값, docling 사용)
python pdf_to_markdown.py document.pdf

# 한국어 PDF
python pdf_to_markdown.py document.pdf -l ko

# 한국어 + 영어 혼합 PDF
python pdf_to_markdown.py document.pdf -l ko en

# 출력 경로 지정
python pdf_to_markdown.py document.pdf -o output -l ko

# MinerU로 변환 (venv-mineru 설치 필요)
python pdf_to_markdown.py document.pdf --tool mineru
```

## 출력 구조

결과물은 `results/<파일명>/` 하위에 저장됩니다. 파일명은 문서에서 인식한 논문 제목이며, 인식하지 못한 경우 원본 PDF 파일명을 사용합니다.

```
results/
  document/
    document.md
    document_img_1.png   # docling: PNG, mineru: images/ 하위 jpg
    document_img_2.png
    ...
```

같은 문서를 다른 `--tool`로 다시 변환하면(인식된 제목이 같다면) 같은 `results/<파일명>/` 폴더에 저장됩니다. 이때 이전 실행 결과물은 폴더째 삭제 후 새로 생성되므로, 두 도구의 산출물이 한 폴더에 섞이지 않습니다.
