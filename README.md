# Doclings

[Docling](https://github.com/DS4SD/docling) 기반 PDF to Markdown 변환기. OCR을 활용하여 PDF에서 텍스트, 표, 이미지를 추출합니다.

## 주요 기능

- OCR 기반 PDF to Markdown 변환
- 표 구조 인식
- 이미지 추출 (PNG 저장)
- 다국어 OCR 지원
- GPU 자동 감지 및 가속

## 설치

```bash
pip install docling torch
```

## 사용법

```bash
python pdf_to_markdown.py <입력PDF> [-o 출력경로] [-l 언어 ...]
```

### 인자

| 인자 | 설명 | 기본값 |
|---|---|---|
| `input` | 변환할 PDF 파일 경로 | (필수) |
| `-o`, `--output` | 출력 기본 디렉토리 | `results` |
| `-l`, `--lang` | OCR 언어 | `en` |

### 예시

```bash
# 영어 PDF (기본값)
python pdf_to_markdown.py document.pdf

# 한국어 PDF
python pdf_to_markdown.py document.pdf -l ko

# 한국어 + 영어 혼합 PDF
python pdf_to_markdown.py document.pdf -l ko en

# 출력 경로 지정
python pdf_to_markdown.py document.pdf -o output -l ko
```

## 출력 구조

결과물은 `results/<파일명>/` 하위에 저장됩니다.

```
results/
  document/
    document.md
    document_img_1.png
    document_img_2.png
    ...
```
