from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .cache import configure_project_cache


configure_project_cache()

from .app import MarkItDownPro

COMMANDS = {"convert"}
DEFAULT_OUTPUT_DIR = Path("output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="markitdownpro",
        description="Convert documents to Markdown with enhanced PDF support.",
    )
    subparsers = parser.add_subparsers(dest="command")

    convert = subparsers.add_parser("convert", help="Convert a file to Markdown.")
    convert.add_argument("input", help="Input file path or supported URI.")
    convert.add_argument(
        "-o",
        "--output",
        help="Output Markdown file. Defaults to output/<input_stem>.md.",
    )
    convert.add_argument(
        "--pdf-mode",
        choices=["academic", "fast"],
        default="academic",
        help="PDF conversion mode. academic uses layout-aware enrichment; fast uses PyMuPDF text extraction.",
    )
    convert.add_argument(
        "--pdf-formula-ocr",
        action="store_true",
        default=True,
        help="Use TexTeller to recognize detected isolated formulas.",
    )
    convert.add_argument(
        "--no-pdf-formula-ocr",
        action="store_false",
        dest="pdf_formula_ocr",
        help="Disable TexTeller formula OCR.",
    )
    convert.add_argument(
        "--assets-dir",
        help="Directory for extracted PDF region images. Defaults next to output file.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = _normalize_argv(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "convert":
        return _convert(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv or argv[0] in COMMANDS or argv[0].startswith("-"):
        return argv
    return ["convert", *argv]


def _convert(args: argparse.Namespace) -> int:
    output = _resolve_output_path(args.input, args.output)
    assets_dir = _resolve_assets_dir(output, args.assets_dir)

    converter = MarkItDownPro(
        pdf_mode=args.pdf_mode,
        formula_ocr=args.pdf_formula_ocr,
        assets_dir=assets_dir,
        assets_base_dir=output.parent,
    )
    result = converter.convert(args.input)
    markdown = _sanitize_markdown(result.markdown)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(output)

    return 0


def _sanitize_markdown(markdown: str) -> str:
    return "".join(
        "\ufffd" if 0xD800 <= ord(char) <= 0xDFFF else char
        for char in markdown
    )


def _resolve_output_path(source: str, value: str | None) -> Path:
    if value:
        return Path(value)

    source_path = Path(source)
    stem = source_path.stem
    if not stem:
        stem = "output"
    return DEFAULT_OUTPUT_DIR / f"{stem}.md"


def _resolve_assets_dir(output: Path, value: str | None) -> Path:
    if value:
        return Path(value)
    return output.parent / f"{output.stem}_assets"


if __name__ == "__main__":
    raise SystemExit(main())
