from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

from .cache import configure_project_cache


configure_project_cache()

from .app import MarkItDownPro

COMMANDS = {"convert"}
DEFAULT_OUTPUT_DIR = Path("output")
MAX_OUTPUT_STEM_CHARS = 72
MAX_OUTPUT_STEM_BYTES = 120


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="markitdownpro",
        description="Convert documents to Markdown with enhanced PDF and DOCX support.",
    )
    subparsers = parser.add_subparsers(dest="command")

    convert = subparsers.add_parser("convert", help="Convert a file to Markdown.")
    convert.add_argument("input", help="Input file path or supported URI.")
    convert.add_argument(
        "-o",
        "--output",
        help=(
            "Output Markdown file or output directory. Defaults to "
            "output/<short_input_stem>/<short_input_stem>.md."
        ),
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
    output, output_dir, output_stem = _resolve_output_layout(args.input, args.output)
    assets_dir = _resolve_assets_dir(output_dir, output_stem, args.assets_dir)

    converter = MarkItDownPro(
        pdf_mode=args.pdf_mode,
        formula_ocr=args.pdf_formula_ocr,
        assets_dir=assets_dir,
        assets_base_dir=output_dir,
    )
    result = converter.convert(args.input)
    markdown = _sanitize_markdown(result.markdown)

    output_dir.mkdir(parents=True, exist_ok=True)
    _copy_source_file(args.input, output_dir, output_stem)
    output.write_text(markdown, encoding="utf-8")
    print(output)

    return 0


def _sanitize_markdown(markdown: str) -> str:
    return "".join(
        "\ufffd" if 0xD800 <= ord(char) <= 0xDFFF else char
        for char in markdown
    )


def _resolve_output_layout(source: str, value: str | None) -> tuple[Path, Path, str]:
    output_stem = _simplify_stem(Path(source).stem or "output")

    if value:
        path = Path(value)
        if path.suffix.lower() == ".md":
            output = path
            output_dir = output.parent
            output_stem = _simplify_stem(output.stem or output_stem)
        else:
            output_dir = path
            output = output_dir / f"{output_stem}.md"
        return output, output_dir, output_stem

    output_dir = DEFAULT_OUTPUT_DIR / output_stem
    output = output_dir / f"{output_stem}.md"
    return output, output_dir, output_stem


def _resolve_assets_dir(output_dir: Path, output_stem: str, value: str | None) -> Path:
    if value:
        return Path(value)
    return output_dir / f"{output_stem}_assets"


def _copy_source_file(source: str, output_dir: Path, output_stem: str) -> None:
    source_path = Path(source)
    if not source_path.is_file():
        return

    target = output_dir / f"{output_stem}{source_path.suffix.lower()}"
    if source_path.resolve() == target.resolve():
        return
    shutil.copy2(source_path, target)


def _simplify_stem(stem: str) -> str:
    normalized = re.sub(r"[\s\u3000]+", "_", stem.strip())
    normalized = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", normalized)
    normalized = re.sub(
        r"(?i)(?:[_-]?[0-9a-f]{12,}|[_-]?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$",
        "",
        normalized,
    )
    normalized = re.sub(r"_+", "_", normalized).strip("._- ")
    if not normalized:
        normalized = "output"
    if _fits_stem_limit(normalized):
        return normalized

    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    char_limit = MAX_OUTPUT_STEM_CHARS - len(digest) - 1
    byte_limit = MAX_OUTPUT_STEM_BYTES - len(digest) - 1
    tokens = [
        token
        for token in re.split(r"[_\-—–（）()\[\]【】,，、]+", normalized)
        if token
    ]
    shortened = ""
    for token in tokens:
        candidate = f"{shortened}_{token}" if shortened else token
        if not _fits_stem_limit(candidate, char_limit, byte_limit):
            break
        shortened = candidate
    if not shortened:
        shortened = _truncate_stem(normalized, char_limit, byte_limit).rstrip("._- ")
    return f"{shortened}-{digest}"


def _fits_stem_limit(
    value: str,
    char_limit: int = MAX_OUTPUT_STEM_CHARS,
    byte_limit: int = MAX_OUTPUT_STEM_BYTES,
) -> bool:
    return len(value) <= char_limit and len(value.encode("utf-8")) <= byte_limit


def _truncate_stem(value: str, char_limit: int, byte_limit: int) -> str:
    chars: list[str] = []
    total_bytes = 0
    for char in value:
        char_bytes = len(char.encode("utf-8"))
        if len(chars) >= char_limit or total_bytes + char_bytes > byte_limit:
            break
        chars.append(char)
        total_bytes += char_bytes
    return "".join(chars)


if __name__ == "__main__":
    raise SystemExit(main())
