import argparse
import logging
from pathlib import Path
from typing import Sequence

from .docling_backend import convert_with_docling
from .errors import ConversionError
from .mineru_backend import convert_with_mineru
from .output import SourceIdentity, publish_directory, staging_directory

_log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert PDF to Markdown.")
    parser.add_argument("input", type=Path, help="Path to the PDF file to convert")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("results"),
        help="Output directory (default: results)",
    )
    parser.add_argument(
        "-l",
        "--lang",
        nargs="+",
        default=["en"],
        help=(
            "OCR language(s) for --tool docling (default: en). "
            "e.g. -l ko en. Ignored when --tool mineru."
        ),
    )
    parser.add_argument(
        "--tool",
        choices=["docling", "mineru"],
        default="docling",
        help="Conversion backend to use (default: docling)",
    )
    parser.add_argument(
        "--no-overwrite",
        dest="overwrite",
        action="store_false",
        help=(
            "Do not replace a title-matched output that belongs to another "
            "input; save as a hash-suffixed folder instead."
        ),
    )
    parser.set_defaults(overwrite=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args(argv)
    input_path = args.input.resolve()
    output_root = args.output.resolve()

    if not input_path.is_file():
        _log.error("File not found or not a regular file: %s", input_path)
        return 1

    if args.tool == "mineru" and args.lang != ["en"]:
        _log.warning("--lang is ignored when --tool mineru is used.")

    try:
        identity = SourceIdentity.from_path(input_path)
        with staging_directory(output_root) as stage:
            if args.tool == "docling":
                title = convert_with_docling(input_path, stage, args.lang)
            else:
                title = convert_with_mineru(input_path, stage)
            result_dir = publish_directory(
                stage,
                output_root,
                title,
                identity,
                args.tool,
                overwrite=args.overwrite,
            )
    except ConversionError as exc:
        _log.error("%s", exc)
        return 1
    except OSError as exc:
        _log.error("File operation failed: %s", exc)
        return 1
    except KeyboardInterrupt:
        _log.error("Conversion interrupted.")
        return 130
    except Exception:
        _log.exception("Unexpected conversion failure.")
        return 1

    _log.info("Result saved: %s", result_dir)
    return 0

