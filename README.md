# MarkItDownPro

MarkItDownPro is a local document-to-Markdown tool built on top of several open-source projects, with a stronger focus on academic and technical PDF conversion.

The goal is not to fork or replace the upstream projects. MarkItDownPro is an integration layer that keeps upstream packages as editable dependencies under `vendor/`, then adds a PDF pipeline that improves reading order, figures, tables, formulas, and local model/cache management.

The current implementation focuses on enhanced PDF-to-Markdown conversion and basic DOCX-to-Markdown conversion. PDF files use the custom layout-aware pipeline; DOCX files are converted through MarkItDown's DOCX converter.

## Relationship to Upstream Projects

MarkItDownPro combines these projects:

- [microsoft/markitdown](https://github.com/microsoft/markitdown): provides the general document conversion interface and non-PDF conversion foundation.
- [PDFMathTranslate/PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate): provides the `pdf2zh` / BabelDOC layout detection components used to locate figures, tables, and isolated formulas in PDF pages.
- [OleehyO/TexTeller](https://github.com/OleehyO/TexTeller): provides formula OCR for detected formula regions.
- [PyMuPDF](https://pymupdf.readthedocs.io/): used directly by MarkItDownPro for PDF text ordering, region rendering, table detection, and PDF repair fallbacks.

This repository keeps those upstream packages in a minimal vendored form so the integration can be developed and tested locally without changing global Python packages. Project-specific logic lives in `src/markitdownpro/`.

## PDF Conversion Preview

Original two-column academic PDF:

![Original PDF page](docs/assets/bastankhah2014-original-pdf.png)

Converted Markdown preview with reconstructed section structure, reading order, and formula rendering:

![Converted Markdown preview](docs/assets/bastankhah2014-markdown-output.png)

## What MarkItDownPro Adds

- A simplified CLI:

  ```bash
  markitdownpro path/to/input.pdf
  ```

- Default output under `output/<short_input_stem>/<short_input_stem>.md`.
- A copy of the original source file saved in the same output folder.
- Extracted PDF and DOCX image assets under `output/<short_input_stem>/<short_input_stem>_assets/`.
- Project-local model cache under `.cache/`, avoiding scattered user-level model files.
- Layout-aware PDF conversion for academic papers and technical documents.
- Better handling for double-column PDFs.
- Formula OCR for detected isolated formulas.
- Figure extraction as Markdown image references.
- Table regions rendered as images when table-to-Markdown extraction is unreliable.
- Basic heading detection for numbered academic sections and Chinese technical documents.
- DOCX heading restoration from Word outline levels and custom heading styles.
- DOCX unsupported vector images such as EMF/WMF are preserved as original assets and represented by displayable PNG placeholders.
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

Long input names are shortened with regex-based cleanup and an 8-character hash suffix. The same shortened stem is used for the output folder, Markdown file, copied source file, and PDF asset folder.

## Installation

Use Python 3.12 and `uv`:

```bash
uv sync
```

## Usage

Convert a PDF and write the result to `output/<short_input_stem>/<short_input_stem>.md`:

```bash
uv run markitdownpro path/to/input.pdf
```

Convert a DOCX file:

```bash
uv run markitdownpro path/to/input.docx
```

Write to a specific file:

```bash
uv run markitdownpro path/to/input.pdf -o path/to/output.md
```

Write under a specific output root directory. MarkItDownPro still creates a
`<short_input_stem>/` folder inside that root:

```bash
uv run markitdownpro path/to/input.pdf -o path/to/output-folder
```

Disable formula OCR for a faster pass:

```bash
uv run markitdownpro path/to/input.pdf --no-pdf-formula-ocr
```

The explicit subcommand form is also supported:

```bash
uv run markitdownpro convert path/to/input.pdf -o path/to/output.md
```

## macOS App

A simple SwiftUI macOS wrapper is available under `macos/MarkItDownProApp/`.

The app supports:

- Dragging a PDF or DOCX file into the window.
- Clicking to choose a file; conversion starts immediately after selection.
- Choosing a model/cache folder in Settings. The app passes it to the CLI through `MARKITDOWNPRO_CACHE_DIR`, so models do not need to be bundled inside the app.
- Choosing an output folder in Settings. By default the app writes to `~/Downloads/markitdown-output`.
  Each converted file is saved in its own subfolder under that output folder.
- Toggling PDF formula OCR before conversion.
- Showing stage-based progress while the CLI is running. PDF progress follows the current processed page over total pages, then finishes with Markdown generation and file writing stages; DOCX progress follows reading, heading restoration, image extraction, Markdown generation, and file writing stages.
- Folding or expanding the command-line log output.

Build the app bundle:

```bash
cd macos/MarkItDownProApp
./build-app.sh
```

If `macos/MarkItDownProApp/Resources/AppIcon.icns` exists, the build script
copies it into the app bundle as the application icon.

The generated app is written to:

```text
macos/MarkItDownProApp/.build/MarkItDownPro.app
```

The Settings window also includes an advanced command path field. In the
packaged app it defaults to the bundled `markitdownpro-cli` launcher; during
local development it falls back to this repository's `.venv/bin/markitdownpro`.

The app bundle is built as a lightweight package: it includes the Python 3.12
runtime, an app-specific pruned virtual environment, and MarkItDownPro
source/vendor code inside the bundle. Model files are not bundled; choose the
model/cache folder in Settings.

During packaging, `build-app.sh` creates `.build/app-venv` from the development
`.venv`, removes bytecode caches, test/example/documentation folders, and keeps
only the small set of command-line entry points needed by the app.

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
