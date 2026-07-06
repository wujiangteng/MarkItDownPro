from __future__ import annotations

import os
import re
import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo

from .cache import configure_babeldoc_cache, configure_model_caches, configure_texteller_cache

PDF_EXTENSIONS = {".pdf"}
PDF_MIME_PREFIXES = ("application/pdf", "application/x-pdf")


@dataclass(frozen=True)
class LayoutRegion:
    label: str
    confidence: float
    x0: int
    y0: int
    x1: int
    y1: int


class EnhancedPdfConverter(DocumentConverter):
    def __init__(
        self,
        *,
        mode: str = "academic",
        formula_ocr: bool = False,
        assets_dir: Path | None = None,
        assets_base_dir: Path | None = None,
    ) -> None:
        self.mode = mode
        self.formula_ocr = formula_ocr
        self.assets_dir = assets_dir
        self.assets_base_dir = assets_base_dir
        self._layout_model = None
        self._formula_model = None
        self._formula_tokenizer = None
        self._latexdet_model = None
        self._textdet_model = None
        self._textrec_model = None

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        extension = (stream_info.extension or "").lower()
        mimetype = (stream_info.mimetype or "").lower()
        return extension in PDF_EXTENSIONS or mimetype.startswith(PDF_MIME_PREFIXES)

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> DocumentConverterResult:
        pdf_bytes = self._repair_missing_extgstate_resources(file_stream.read())

        if self.mode == "fast":
            return DocumentConverterResult(markdown=self._convert_fast(pdf_bytes))

        try:
            markdown = self._convert_academic(pdf_bytes)
        except Exception as exc:
            markdown = (
                "<!-- markitdownpro: enhanced PDF conversion failed; "
                f"used PyMuPDF fallback: {type(exc).__name__}: {exc} -->\n\n"
                + self._convert_fast(pdf_bytes)
            )
            return DocumentConverterResult(markdown=markdown)

        if not markdown.strip():
            return DocumentConverterResult(markdown=self._convert_fast(pdf_bytes))

        return DocumentConverterResult(markdown=markdown)

    def _repair_missing_extgstate_resources(self, pdf_bytes: bytes) -> bytes:
        import fitz

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception:
            return pdf_bytes

        patched = False
        try:
            for page in doc:
                page_extgstates = self._page_extgstate_map(doc, page)
                if not page_extgstates:
                    continue

                for xobject in page.get_xobjects():
                    xref, name = xobject[0], xobject[1]
                    if doc.xref_get_key(xref, "Subtype") != ("name", "/Form"):
                        continue

                    stream = doc.xref_stream(xref) or b""
                    names = sorted(
                        {
                            match.decode()
                            for match in re.findall(rb"/(GS[\w]+)\s+gs\b", stream)
                        }
                    )
                    missing = [name for name in names if name in page_extgstates]
                    if not missing:
                        continue

                    obj = doc.xref_object(xref, compressed=False)
                    replacement = self._with_extgstate_resources(
                        obj,
                        {name: page_extgstates[name] for name in missing},
                    )
                    if replacement != obj:
                        doc.update_object(xref, replacement)
                        patched = True

            if not patched:
                return pdf_bytes
            return doc.tobytes(garbage=3, deflate=True)
        except Exception:
            return pdf_bytes
        finally:
            doc.close()

    def _page_extgstate_map(self, doc: Any, page: Any) -> dict[str, str]:
        kind, value = doc.xref_get_key(page.xref, "Resources")
        if kind == "xref":
            value = doc.xref_object(int(value.split()[0]), compressed=False)
        elif kind != "dict":
            return {}

        return {
            match.group(1): match.group(2)
            for match in re.finditer(r"/(GS[\w]+)\s+(\d+\s+0\s+R)", value)
        }

    def _with_extgstate_resources(
        self,
        obj: str,
        extgstates: dict[str, str],
    ) -> str:
        entries = " ".join(f"/{name} {xref}" for name, xref in extgstates.items())
        extgstate = f"/ExtGState << {entries} >>"
        if re.search(r"/Resources\s*<<\s*>>", obj):
            return re.sub(
                r"/Resources\s*<<\s*>>",
                f"/Resources << {extgstate} >>",
                obj,
                count=1,
            )
        if "/Resources <<" in obj and "/ExtGState" not in obj:
            return obj.replace("/Resources <<", f"/Resources << {extgstate} ", 1)
        return obj

    def _convert_fast(self, pdf_bytes: bytes) -> str:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        chunks: list[str] = []
        for page_index, page in enumerate(doc):
            text = self._extract_ordered_text(page).strip()
            if text:
                chunks.append(f"<!-- page {page_index + 1} -->\n\n{text}")
        doc.close()
        return "\n\n".join(chunks)

    def _convert_academic(self, pdf_bytes: bytes) -> str:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        chunks: list[str] = []

        if self.assets_dir is not None:
            self.assets_dir.mkdir(parents=True, exist_ok=True)

        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            chunks.append(f"<!-- page {page_number} -->")

            try:
                regions = self._detect_layout_regions(page)
            except Exception as exc:
                chunks.append(
                    "<!-- markitdownpro: layout detection skipped on "
                    f"page {page_number}: {type(exc).__name__}: {exc} -->"
                )
                regions = []

            rich_regions = [
                region
                for region in regions
                if region.label in {"figure", "table", "isolate_formula"}
            ]
            rich_regions.extend(self._find_table_regions(page, rich_regions))
            rich_regions = self._dedupe_regions(rich_regions)

            region_items: list[dict[str, Any]] = []
            replaced_regions: list[LayoutRegion] = []
            for region_index, region in enumerate(rich_regions, start=1):
                content = self._region_markdown(page, page_number, region_index, region)
                if content:
                    region_items.append(self._region_item(region, content))
                    replaced_regions.append(region)

            page_items = self._text_blocks(page, exclude_regions=replaced_regions)
            page_items.extend(region_items)

            text = self._items_to_ordered_markdown(page, page_items).strip()
            if text:
                chunks.append(text)

        doc.close()
        return "\n\n".join(chunk for chunk in chunks if chunk.strip())

    def _extract_ordered_text(self, page: Any) -> str:
        blocks = self._text_blocks(page)
        return self._items_to_ordered_markdown(page, blocks)

    def _items_to_ordered_markdown(
        self, page: Any, blocks: list[dict[str, Any]]
    ) -> str:
        if not blocks:
            return ""

        page_width = float(page.rect.width)
        column_blocks = [b for b in blocks if b["width"] < page_width * 0.68]
        if len(column_blocks) < 4:
            return "\n\n".join(
                b["text"] for b in sorted(blocks, key=lambda b: (b["y0"], b["x0"]))
            )

        return "\n\n".join(
            b["text"] for b in self._sort_two_column_blocks(blocks, page_width)
        )

    def _text_blocks(
        self, page: Any, exclude_regions: list[LayoutRegion] | None = None
    ) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        page_height = float(page.rect.height)
        page_width = float(page.rect.width)
        exclude_regions = exclude_regions or []
        body_size = self._body_font_size(page)

        for raw in page.get_text("dict").get("blocks", []):
            if raw.get("type") != 0:
                continue
            text, stats = self._block_text_and_stats(raw)
            if not text:
                continue
            x0, y0, x1, y1 = raw["bbox"]
            if self._is_repeating_margin_text(text, y0, y1, page_height):
                continue
            block = {
                "x0": float(x0),
                "y0": float(y0),
                "x1": float(x1),
                "y1": float(y1),
                "width": float(x1 - x0),
                "text": self._format_heading(
                    text,
                    block={
                        "x0": float(x0),
                        "y0": float(y0),
                        "x1": float(x1),
                        "y1": float(y1),
                        "width": float(x1 - x0),
                        **stats,
                    },
                    body_size=body_size,
                    page_width=page_width,
                ),
            }
            if self._overlaps_excluded_region(block, exclude_regions):
                continue
            blocks.append(block)
        return blocks

    def _body_font_size(self, page: Any) -> float:
        sizes: list[float] = []
        page_height = float(page.rect.height)
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            x0, y0, x1, y1 = block["bbox"]
            if self._is_repeating_margin_text("", y0, y1, page_height):
                continue
            text, stats = self._block_text_and_stats(block)
            if not text or len(text) < 12:
                continue
            sizes.extend(stats["sizes"])
        return statistics.median(sizes) if sizes else 10.5

    def _block_text_and_stats(self, block: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        parts: list[str] = []
        sizes: list[float] = []
        fonts: list[str] = []
        flags: list[int] = []
        for line in block.get("lines", []):
            line_parts: list[str] = []
            for span in line.get("spans", []):
                value = span.get("text", "")
                line_parts.append(value)
                if value.strip():
                    sizes.append(float(span.get("size", 0.0)))
                    fonts.append(span.get("font", ""))
                    flags.append(int(span.get("flags", 0)))
            parts.append("".join(line_parts))

        text = " ".join(" ".join(parts).split())
        font = " ".join(fonts)
        return text, {
            "sizes": sizes,
            "font_size": statistics.median(sizes) if sizes else 0.0,
            "max_font_size": max(sizes) if sizes else 0.0,
            "font": font,
            "is_bold": bool(re.search(r"bold|hei|simhei|黑体", font, re.I))
            or any(flag & 16 for flag in flags),
            "is_italic": bool(re.search(r"italic|ital|oblique", font, re.I))
            or any(flag & 2 for flag in flags),
        }

    def _format_heading(
        self,
        text: str,
        *,
        block: dict[str, Any],
        body_size: float,
        page_width: float,
    ) -> str:
        normalized = " ".join(text.split())
        if normalized == "a b s t r a c t":
            return "## Abstract"
        if normalized == "a r t i c l e i n f o":
            return "## Article info"
        level = self._heading_level(normalized, block, body_size, page_width)
        if level is not None:
            combined = self._format_combined_numbered_headings(normalized)
            if combined:
                return combined
            heading, rest = self._split_heading_prefix(normalized)
            if rest:
                return f"{'#' * level} {heading}\n\n{rest}"
            return f"{'#' * level} {normalized}"
        return normalized

    def _split_heading_prefix(self, text: str) -> tuple[str, str | None]:
        match = re.match(
            r"^((?:\d{1,2}(?:\.\d{1,2})+)\s+.{2,24}?)(\s+(?:按照|简述|根据|基于|例[：:]|本|按|如|应|为|项目|图|表).+)$",
            text,
        )
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return text, None

    def _format_combined_numbered_headings(self, text: str) -> str | None:
        matches = list(
            re.finditer(
                r"(?<!\S)(\d{1,2}(?:\.\d{1,2})*\.?)\s+([A-Z][A-Za-z][^0-9]{2,80}?)(?=\s+\d{1,2}(?:\.\d{1,2})*\.?\s+[A-Z]|\s*$)",
                text,
            )
        )
        if len(matches) < 2 or matches[0].start() != 0:
            return None

        lines: list[str] = []
        for match in matches:
            number = match.group(1).rstrip(".")
            title = match.group(2).strip()
            level = min(2 + number.count("."), 6)
            lines.append(f"{'#' * level} {number}. {title}")
        return "\n\n".join(lines)

    def _heading_level(
        self,
        text: str,
        block: dict[str, Any],
        body_size: float,
        page_width: float,
    ) -> int | None:
        if self._looks_like_toc_or_table_line(text, block, page_width):
            return None

        length = len(text)
        font_size = block["font_size"]
        styled = block["is_bold"] or block.get("is_italic", False)
        is_prominent = font_size >= body_size + 1.0 or (
            styled and font_size >= body_size - 0.2
        )
        if font_size < body_size - 0.2 and not is_prominent:
            return None

        is_short_left_line = (
            block["x0"] <= page_width * 0.22
            and length <= 36
            and font_size >= body_size - 0.2
        )

        if re.match(r"^第[一二三四五六七八九十百\d]+[章节篇部分]\S*", text):
            return 2 if is_prominent or length <= 32 else None

        if re.match(r"^附件\d+[：:]\s*\S+", text):
            return 2 if is_prominent and length <= 40 else None

        if re.match(r"^\d{1,2}\s+[\u4e00-\u9fffA-Za-z]", text):
            if self._looks_like_table_entry(text):
                return None
            return 2 if is_prominent or is_short_left_line else None

        match = re.match(r"^(\d{1,2}(?:\.\d{1,2})+)\.?\s+\S+", text)
        if match and (is_prominent or is_short_left_line):
            depth = match.group(1).count(".")
            return min(2 + depth, 6)

        if re.match(r"^\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z].*", text):
            return 2 if is_prominent or is_short_left_line else None

        if block["is_bold"] and font_size >= body_size + 2.0 and length <= 40:
            return 2

        return None

    def _looks_like_toc_or_table_line(
        self,
        text: str,
        block: dict[str, Any],
        page_width: float,
    ) -> bool:
        if "...." in text or re.search(r"\.{4,}\s*\d+\s*$", text):
            return True
        if re.match(r"^[a-z]{3,20}$", text):
            return True
        if re.match(r"^(Figure|Fig\.|Table)\s+\d+", text, re.I):
            return True
        if re.match(r"^(Citation|Received|Revised|Accepted|Published|Copyright)\b", text):
            return True
        if re.match(r"^\d{3,}\s+", text):
            return True
        if re.search(r"\b[NSWE]\b|°[NSEW]|XXXXX", text):
            return True
        if block["width"] >= page_width * 0.68 and re.search(r"\s\d{1,3}$", text):
            return True
        if len(text) > 90:
            return True
        if re.match(r"^\d{1,2}\s+.*[。；;]$", text):
            return True
        if re.search(r"https?://|\\\\|/|OA\+|\.cn\b", text):
            return True
        if re.match(r"^[A-Z]\d?\s+", text):
            return True
        if re.match(r"^\d+[.、]\s*[\u4e00-\u9fff].*[。；;]?$", text) and len(text) > 36:
            return True
        return False

    def _looks_like_table_entry(self, text: str) -> bool:
        return bool(
            re.search(
                r"(地址|账号|权限|密码|管理员|平台|联系|邮箱|OA|http|www|\\\\|\.cn\b)",
                text,
                re.I,
            )
        )

    def _overlaps_excluded_region(
        self, block: dict[str, Any], regions: list[LayoutRegion]
    ) -> bool:
        for region in regions:
            threshold = 0.08 if region.label == "isolate_formula" else 0.35
            if self._overlap_ratio(block, region) > threshold:
                return True
        return False

    def _overlap_ratio(self, block: dict[str, Any], region: LayoutRegion) -> float:
        x0 = max(block["x0"], region.x0)
        y0 = max(block["y0"], region.y0)
        x1 = min(block["x1"], region.x1)
        y1 = min(block["y1"], region.y1)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        overlap = (x1 - x0) * (y1 - y0)
        block_area = max((block["x1"] - block["x0"]) * (block["y1"] - block["y0"]), 1)
        return overlap / block_area

    def _region_item(self, region: LayoutRegion, text: str) -> dict[str, Any]:
        return {
            "x0": float(region.x0),
            "y0": float(region.y0),
            "x1": float(region.x1),
            "y1": float(region.y1),
            "width": float(region.x1 - region.x0),
            "text": text,
        }

    def _region_markdown(
        self,
        page: Any,
        page_number: int,
        region_index: int,
        region: LayoutRegion,
    ) -> str | None:
        content = None
        if region.label == "isolate_formula":
            latex = self._recognize_formula(page, region)
            if latex:
                content = f"$$\n{latex}\n$$"
            else:
                return "<!-- formula OCR unavailable -->"

        elif region.label == "table":
            return self._region_asset_markdown(page, page_number, region_index, region)

        if content is not None:
            return content

        asset_ref = self._save_region_asset(page, page_number, region_index, region)
        if not asset_ref:
            return None

        alt = f"{region.label} page {page_number}"
        return f"![{alt}]({asset_ref})"

    def _region_asset_markdown(
        self,
        page: Any,
        page_number: int,
        region_index: int,
        region: LayoutRegion,
    ) -> str | None:
        asset_ref = self._save_region_asset(page, page_number, region_index, region)
        if not asset_ref:
            return None
        alt = f"{region.label} page {page_number}"
        return f"![{alt}]({asset_ref})"

    def _is_repeating_margin_text(
        self, text: str, y0: float, y1: float, page_height: float
    ) -> bool:
        if y1 < page_height * 0.09:
            return True
        if y1 < page_height * 0.18 and (
            text == "Renewable Energy"
            or text.startswith("Contents lists")
            or text.startswith("journal homepage:")
            or " / Renewable Energy " in text
        ):
            return True
        if y0 > page_height * 0.94:
            return True
        if y0 > page_height * 0.90 and (
            text.startswith("Please cite this article")
            or "doi.org/" in text
            or "All rights reserved" in text
        ):
            return True
        if y0 > page_height * 0.86 and text.startswith("* Corresponding author."):
            return True
        return False

    def _sort_two_column_blocks(
        self, blocks: list[dict[str, Any]], page_width: float
    ) -> list[dict[str, Any]]:
        center_x = page_width / 2
        ordered: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []

        for block in sorted(blocks, key=lambda b: (b["y0"], b["x0"])):
            spans_center = block["x0"] < center_x < block["x1"]
            is_full_width = block["width"] >= page_width * 0.68
            if spans_center and is_full_width:
                ordered.extend(self._sort_column_band(pending, center_x))
                pending = []
                ordered.append(block)
            else:
                pending.append(block)

        ordered.extend(self._sort_column_band(pending, center_x))
        return ordered

    def _sort_column_band(
        self, blocks: list[dict[str, Any]], center_x: float
    ) -> list[dict[str, Any]]:
        ordered: list[dict[str, Any]] = []
        for segment in self._split_vertical_segments(blocks):
            split_x = self._column_split_x(segment, center_x)
            left = [b for b in segment if b["x0"] < split_x]
            right = [b for b in segment if b["x0"] >= split_x]
            ordered.extend(sorted(left, key=lambda b: (b["y0"], b["x0"])))
            ordered.extend(sorted(right, key=lambda b: (b["y0"], b["x0"])))
        return ordered

    def _column_split_x(
        self, blocks: list[dict[str, Any]], fallback: float
    ) -> float:
        starts = sorted({round(b["x0"], 1) for b in blocks})
        if len(starts) < 2:
            return fallback

        left_starts = [x for x in starts if x < fallback]
        right_starts = [x for x in starts if x > fallback]
        if left_starts and right_starts:
            return (max(left_starts) + min(right_starts)) / 2

        best_gap = 0.0
        best_split = fallback
        for left, right in zip(starts, starts[1:]):
            gap = right - left
            if gap > best_gap:
                best_gap = gap
                best_split = left + gap / 2

        return best_split if best_gap >= 36 else fallback

    def _split_vertical_segments(
        self, blocks: list[dict[str, Any]], gap_threshold: float = 24.0
    ) -> list[list[dict[str, Any]]]:
        segments: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_bottom: float | None = None

        for block in sorted(blocks, key=lambda b: (b["y0"], b["x0"])):
            if (
                current
                and current_bottom is not None
                and block["y0"] - current_bottom > gap_threshold
            ):
                segments.append(current)
                current = []
                current_bottom = None

            current.append(block)
            current_bottom = (
                block["y1"]
                if current_bottom is None
                else max(current_bottom, block["y1"])
            )

        if current:
            segments.append(current)
        return segments

    def _detect_layout_regions(self, page: Any) -> list[LayoutRegion]:
        import numpy as np

        model = self._get_layout_model()
        pix = page.get_pixmap()
        image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            image = image[:, :, :3]

        result = model.predict(image[:, :, ::-1], imgsz=int(pix.height / 32) * 32)[0]
        regions: list[LayoutRegion] = []
        for box in result.boxes:
            label = result.names[int(box.cls)]
            x0, y0, x1, y1 = [int(v) for v in box.xyxy]
            regions.append(
                LayoutRegion(
                    label=label,
                    confidence=float(box.conf),
                    x0=max(0, x0),
                    y0=max(0, y0),
                    x1=min(pix.width, x1),
                    y1=min(pix.height, y1),
                )
            )
        return sorted(regions, key=lambda r: (r.y0, r.x0))

    def _get_layout_model(self) -> Any:
        if self._layout_model is None:
            configure_babeldoc_cache()
            from pdf2zh.doclayout import DocLayoutModel, set_backend

            set_backend("cpu")
            self._layout_model = DocLayoutModel.load_available()
        return self._layout_model

    def _recognize_formula(self, page: Any, region: LayoutRegion) -> str | None:
        if not self.formula_ocr:
            return None

        image = self._render_region(page, region, scale=4.0, padding=4.0)
        if image is None:
            return None

        model, tokenizer = self._get_formula_model()
        from texteller import img2latex

        try:
            raw = img2latex(
                model=model,
                tokenizer=tokenizer,
                images=[image],
                out_format="katex",
                keep_style=False,
            )[0]
            return self._clean_latex(raw)
        except Exception:
            return None

    def _clean_latex(self, value: str) -> str | None:
        text = value.strip()
        text = re.sub(r"^```(?:latex|tex|katex|math)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text).strip()

        while True:
            if text.startswith("$$") and text.endswith("$$"):
                text = text[2:-2].strip()
                continue
            if text.startswith("$") and text.endswith("$"):
                text = text[1:-1].strip()
                continue
            break

        lines = [
            line
            for line in text.splitlines()
            if line.strip() not in {"$", "$$"}
        ]
        text = "\n".join(lines).strip()
        return text or None

    def _get_formula_model(self) -> tuple[Any, Any]:
        if self._formula_model is None or self._formula_tokenizer is None:
            configure_model_caches()
            from texteller import load_model, load_tokenizer

            self._formula_model = load_model()
            self._formula_tokenizer = load_tokenizer()
        return self._formula_model, self._formula_tokenizer

    def _recognize_region_with_texteller(
        self, page: Any, region: LayoutRegion
    ) -> str | None:
        if not self.formula_ocr:
            return None

        pix = self._render_region_pixmap(page, region, scale=3.0, padding=2.0)
        if pix is None:
            return None

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            pix.save(tmp.name)
            latexdet_model, textdet_model, textrec_model = self._get_texteller_ocr_models()
            formula_model, tokenizer = self._get_formula_model()

            from texteller import paragraph2md

            try:
                text = paragraph2md(
                    img_path=tmp.name,
                    latexdet_model=latexdet_model,
                    textdet_model=textdet_model,
                    textrec_model=textrec_model,
                    latexrec_model=formula_model,
                    tokenizer=tokenizer,
                )
            except Exception:
                return None
        return text.strip() or None

    def _get_texteller_ocr_models(self) -> tuple[Any, Any, Any]:
        if (
            self._latexdet_model is None
            or self._textdet_model is None
            or self._textrec_model is None
        ):
            configure_texteller_cache()
            from texteller import (
                load_latexdet_model,
                load_textdet_model,
                load_textrec_model,
            )

            self._latexdet_model = load_latexdet_model()
            self._textdet_model = load_textdet_model()
            self._textrec_model = load_textrec_model()
        return self._latexdet_model, self._textdet_model, self._textrec_model

    def _extract_table_markdown(self, page: Any, region: LayoutRegion | None) -> str | None:
        rect = self._region_rect(page, region, padding=1.0) if region is not None else None
        try:
            tables = page.find_tables(clip=rect)
        except Exception:
            return None

        if not tables.tables:
            return None

        for table in tables.tables:
            rows = table.extract()
            markdown = self._rows_to_markdown(rows)
            if markdown:
                return markdown
        return None

    def _find_table_regions(
        self, page: Any, existing_regions: list[LayoutRegion]
    ) -> list[LayoutRegion]:
        try:
            tables = page.find_tables()
        except Exception:
            return []

        regions: list[LayoutRegion] = []
        for table in tables.tables:
            x0, y0, x1, y1 = table.bbox
            region = LayoutRegion(
                label="table",
                confidence=1.0,
                x0=int(x0),
                y0=int(y0),
                x1=int(x1),
                y1=int(y1),
            )
            if not any(self._regions_overlap(region, other) > 0.6 for other in existing_regions):
                regions.append(region)
        return regions

    def _regions_overlap(self, first: LayoutRegion, second: LayoutRegion) -> float:
        x0 = max(first.x0, second.x0)
        y0 = max(first.y0, second.y0)
        x1 = min(first.x1, second.x1)
        y1 = min(first.y1, second.y1)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        overlap = (x1 - x0) * (y1 - y0)
        first_area = max((first.x1 - first.x0) * (first.y1 - first.y0), 1)
        return overlap / first_area

    def _dedupe_regions(self, regions: list[LayoutRegion]) -> list[LayoutRegion]:
        kept: list[LayoutRegion] = []
        for region in sorted(regions, key=lambda r: r.confidence, reverse=True):
            if any(
                region.label == other.label
                and (
                    self._regions_overlap(region, other) > 0.8
                    or self._regions_overlap(other, region) > 0.8
                )
                for other in kept
            ):
                continue
            kept.append(region)
        return sorted(kept, key=lambda r: (r.y0, r.x0))

    def _rows_to_markdown(self, rows: list[list[Any]]) -> str | None:
        normalized = [
            [self._normalize_table_cell(cell) for cell in row]
            for row in rows
            if row and any(self._normalize_table_cell(cell) for cell in row)
        ]
        if not normalized:
            return None

        width = max(len(row) for row in normalized)
        normalized = [row + [""] * (width - len(row)) for row in normalized]

        header = normalized[0]
        body = normalized[1:]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        lines.extend("| " + " | ".join(row) + " |" for row in body)
        return "\n".join(lines)

    def _normalize_table_cell(self, value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).split()).replace("|", "\\|")

    def _save_region_asset(
        self,
        page: Any,
        page_number: int,
        region_index: int,
        region: LayoutRegion,
    ) -> str | None:
        if self.assets_dir is None:
            return None

        scale = 3.0 if region.label == "table" else 2.0
        padding = 3.0 if region.label == "table" else 2.0
        pix = self._render_region_pixmap(page, region, scale=scale, padding=padding)
        if pix is None:
            return None

        filename = f"page-{page_number:04d}-{region_index:02d}-{region.label}.png"
        path = self.assets_dir / filename
        pix.save(str(path))
        return self._asset_markdown_path(path)

    def _asset_markdown_path(self, path: Path) -> str:
        if self.assets_base_dir is None:
            return path.as_posix()
        try:
            return Path(os.path.relpath(path, self.assets_base_dir)).as_posix()
        except ValueError:
            return path.as_posix()

    def _render_region(
        self,
        page: Any,
        region: LayoutRegion,
        *,
        scale: float = 1.0,
        padding: float = 0.0,
    ):
        import numpy as np

        pix = self._render_region_pixmap(
            page,
            region,
            scale=scale,
            padding=padding,
        )
        if pix is None:
            return None

        image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            image = image[:, :, :3]
        return image

    def _render_region_pixmap(
        self,
        page: Any,
        region: LayoutRegion,
        *,
        scale: float = 1.0,
        padding: float = 0.0,
    ):
        import fitz

        rect = self._region_rect(page, region, padding=padding)
        if rect is None:
            return None
        matrix = fitz.Matrix(scale, scale) if scale != 1.0 else None
        return page.get_pixmap(matrix=matrix, clip=rect)

    def _region_rect(self, page: Any, region: LayoutRegion, *, padding: float = 0.0):
        import fitz

        rect = fitz.Rect(region.x0, region.y0, region.x1, region.y1)
        if padding:
            rect = rect + (-padding, -padding, padding, padding)
            rect = rect & page.rect
        if rect.is_empty or rect.width < 2 or rect.height < 2:
            return None
        return rect
