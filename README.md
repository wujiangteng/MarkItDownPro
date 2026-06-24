# MarkItDownPro

MarkItDownPro is a local document-to-Markdown tool built on top of several open-source projects, with a stronger focus on academic and technical PDF conversion.

The goal is not to fork or replace the upstream projects. MarkItDownPro is an integration layer that keeps upstream packages as editable dependencies under `vendor/`, then adds a PDF pipeline that improves reading order, figures, tables, formulas, and local model/cache management.

## Relationship to Upstream Projects

MarkItDownPro combines these projects:

- [microsoft/markitdown](https://github.com/microsoft/markitdown): provides the general document conversion interface and non-PDF conversion foundation.
- [PDFMathTranslate/PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate): provides the `pdf2zh` / BabelDOC layout detection components used to locate figures, tables, and isolated formulas in PDF pages.
- [OleehyO/TexTeller](https://github.com/OleehyO/TexTeller): provides formula OCR for detected formula regions.
- [PyMuPDF](https://pymupdf.readthedocs.io/): used directly by MarkItDownPro for PDF text ordering, region rendering, table detection, and PDF repair fallbacks.

This repository keeps those upstream packages in a minimal vendored form so the integration can be developed and tested locally without changing global Python packages. Project-specific logic lives in `src/markitdownpro/`.

## What MarkItDownPro Adds

- A simplified CLI:

  ```bash
  markitdownpro path/to/input.pdf
  ```

- Default output under `output/<input_stem>.md`.
- Extracted image assets under `output/<input_stem>_assets/`.
- Project-local model cache under `.cache/`, avoiding scattered user-level model files.
- Layout-aware PDF conversion for academic papers and technical documents.
- Better handling for double-column PDFs.
- Formula OCR for detected isolated formulas.
- Figure extraction as Markdown image references.
- Table regions rendered as images when table-to-Markdown extraction is unreliable.
- Basic heading detection for numbered academic sections and Chinese technical documents.
- PDF repair fallback for some malformed resource dictionaries seen in real-world PDFs.

## Layout

```text
.
├── src/markitdownpro/          # MarkItDownPro integration package and CLI
├── vendor/                     # Minimal editable upstream dependency roots
│   ├── markitdown/
│   ├── pdf2zh/
│   └── texteller/
├── pyproject.toml              # Root package and uv dependency configuration
├── uv.lock
└── README.md
```

`examples/`, `output/`, `.cache/`, and `.venv/` are intentionally ignored by Git.

## Installation

Use Python 3.12 and `uv`:

```bash
uv sync
```

## Usage

Convert a PDF and write the result to `output/<input_stem>.md`:

```bash
uv run markitdownpro path/to/input.pdf
```

Write to a specific file:

```bash
uv run markitdownpro path/to/input.pdf -o path/to/output.md
```

Disable formula OCR for a faster pass:

```bash
uv run markitdownpro path/to/input.pdf --no-pdf-formula-ocr
```

The explicit subcommand form is also supported:

```bash
uv run markitdownpro convert path/to/input.pdf -o path/to/output.md
```

## Model Cache

Runtime model downloads are kept inside the project by default:

```text
.cache/
├── babeldoc/      # PDFMathTranslate/BabelDOC doclayout models
├── huggingface/   # TexTeller main model and tokenizer
├── texteller/     # TexTeller helper ONNX OCR models
└── torch/
```

Override the root only when needed:

```bash
MARKITDOWNPRO_CACHE_DIR=/path/to/cache uv run markitdownpro path/to/input.pdf
```

## Development

```bash
uv sync
uv run python -m compileall src
```

Keep integration changes in `src/markitdownpro/`. Avoid modifying vendored upstream code unless the change is required for local packaging or is being prepared deliberately as an upstream patch.

## Notes

PDF conversion quality depends on PDF structure and layout detection quality. For tables, MarkItDownPro currently prefers preserving visual fidelity by inserting detected table regions as images instead of forcing unreliable Markdown tables.
