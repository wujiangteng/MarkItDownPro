from __future__ import annotations

import io
import re
from zipfile import ZipFile
from pathlib import Path
from typing import Any, BinaryIO, Callable
from xml.etree import ElementTree as ET

import mammoth
from bs4 import BeautifulSoup, Tag
from PIL import Image, ImageDraw
from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo
from markitdown.converter_utils.docx.pre_process import _convert_omath_to_latex
from markitdown.converters._html_converter import HtmlConverter


DOCX_EXTENSIONS = {".docx"}
DOCX_MIME_PREFIXES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

IMAGE_EXTENSIONS = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/tiff": ".tiff",
    "image/x-emf": ".emf",
    "image/x-wmf": ".wmf",
}
DISPLAYABLE_IMAGE_EXTENSIONS = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
}


class EnhancedDocxConverter(DocumentConverter):
    def __init__(
        self,
        *,
        assets_dir: Path | None = None,
        assets_base_dir: Path | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.assets_dir = assets_dir
        self.assets_base_dir = assets_base_dir
        self.progress_callback = progress_callback
        self._html_converter = HtmlConverter()
        self._image_index = 0
        self._image_total = 0

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        extension = (stream_info.extension or "").lower()
        mimetype = (stream_info.mimetype or "").lower()
        return extension in DOCX_EXTENSIONS or mimetype.startswith(DOCX_MIME_PREFIXES)

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> DocumentConverterResult:
        self._image_index = 0
        docx_bytes = file_stream.read()
        self._image_total = self._count_images(docx_bytes)
        self._emit_progress(stage="docx", current=1, total=4, message="正在读取 DOCX")
        style_map = self._style_map(docx_bytes, kwargs.get("style_map", None))
        self._emit_progress(stage="docx", current=2, total=4, message="正在恢复标题层级")
        pre_processed = self._pre_process_docx(docx_bytes)
        image_message = "正在提取图片" if self._image_total else "未检测到图片，正在转换正文"
        self._emit_progress(stage="docx", current=3, total=4, message=image_message)
        result = mammoth.convert_to_html(
            pre_processed,
            style_map=style_map,
            convert_image=mammoth.images.img_element(self._image_attributes),
        )
        self._emit_progress(stage="markdown", current=1, total=1, message="正在生成 Markdown")
        return self._convert_html_to_markdown(result.value, **kwargs)

    def _pre_process_docx(self, docx_bytes: bytes) -> BinaryIO:
        output_docx = io.BytesIO()
        with ZipFile(io.BytesIO(docx_bytes), mode="r") as zip_input:
            with ZipFile(output_docx, mode="w") as zip_output:
                zip_output.comment = zip_input.comment
                for item in zip_input.infolist():
                    content = zip_input.read(item.filename)
                    if (
                        item.filename.startswith("word/")
                        and item.filename.endswith(".xml")
                        and b"oMath" in content
                    ):
                        try:
                            content = self._pre_process_math(content)
                        except Exception:
                            pass
                    zip_output.writestr(item, content)
        output_docx.seek(0)
        return output_docx

    def _pre_process_math(self, content: bytes) -> bytes:
        soup = BeautifulSoup(content.decode(), features="xml")
        for tag in list(soup.find_all("oMathPara")):
            self._replace_omath_para(soup, tag)
        for tag in list(soup.find_all("oMath")):
            self._replace_omath(soup, tag, block=False)
        return str(soup).encode()

    def _replace_omath_para(self, soup: BeautifulSoup, tag: Tag) -> None:
        paragraph = soup.new_tag("w:p")
        for child in tag.find_all("oMath"):
            paragraph.append(self._omath_replacement(soup, child, block=True))
        tag.replace_with(paragraph)

    def _replace_omath(self, soup: BeautifulSoup, tag: Tag, *, block: bool) -> None:
        tag.replace_with(self._omath_replacement(soup, tag, block=block))

    def _omath_replacement(self, soup: BeautifulSoup, tag: Tag, *, block: bool) -> Tag:
        latex = self._omath_latex(tag)
        text = f"$${latex}$$" if block else f"${latex}$"
        text_tag = soup.new_tag("w:t")
        text_tag.string = text
        run_tag = soup.new_tag("w:r")
        run_tag.append(text_tag)
        return run_tag

    def _omath_latex(self, tag: Tag) -> str:
        try:
            latex = _convert_omath_to_latex(tag)
        except Exception:
            latex = self._omath_plain_text(tag)
        latex = self._sanitize_latex(latex)
        return latex or self._sanitize_latex(self._omath_plain_text(tag))

    def _omath_plain_text(self, tag: Tag) -> str:
        return "".join(text.get_text() for text in tag.find_all("t"))

    def _sanitize_latex(self, latex: str) -> str:
        latex = latex.strip()
        replacements = {
            "\\m ": "\\mu ",
            "\\n ": "\\nu ",
            "\\ta ": "\\tau ",
            "×": "\\times ",
            "≤": "\\le ",
            "≥": "\\ge ",
            "≠": "\\ne ",
            "±": "\\pm ",
        }
        for source, target in replacements.items():
            latex = latex.replace(source, target)
        return latex

    def _convert_html_to_markdown(self, html: str, **kwargs: Any) -> DocumentConverterResult:
        html, tables = self._extract_merged_tables(html)
        result = self._html_converter.convert_string(html, **kwargs)
        markdown = result.markdown
        for placeholder, table_html in tables.items():
            markdown = markdown.replace(placeholder, table_html)
        markdown = self._restore_math_markdown(markdown)
        return DocumentConverterResult(markdown=markdown, title=result.title)

    def _extract_merged_tables(self, html: str) -> tuple[str, dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        tables: dict[str, str] = {}
        for index, table in enumerate(soup.find_all("table"), start=1):
            if not self._has_merged_cells(table):
                continue
            placeholder = f"MARKITDOWNPROMERGEDTABLE{index:04d}"
            tables[placeholder] = table.decode(formatter="html")
            marker = soup.new_tag("p")
            marker.string = placeholder
            table.replace_with(marker)
        return str(soup), tables

    def _has_merged_cells(self, table: Any) -> bool:
        for cell in table.find_all(["td", "th"]):
            if self._span_value(cell.get("rowspan")) > 1:
                return True
            if self._span_value(cell.get("colspan")) > 1:
                return True
        return False

    def _span_value(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 1

    def _restore_math_markdown(self, markdown: str) -> str:
        restored: list[str] = []
        index = 0
        while index < len(markdown):
            if markdown.startswith("$$", index):
                end = markdown.find("$$", index + 2)
                if end == -1:
                    restored.append(markdown[index:])
                    break
                content = self._unescape_markdown_math(markdown[index + 2 : end])
                restored.append(f"$${content}$$")
                index = end + 2
                continue
            if markdown[index] == "$":
                end = markdown.find("$", index + 1)
                if end == -1:
                    restored.append(markdown[index:])
                    break
                content = self._unescape_markdown_math(markdown[index + 1 : end])
                restored.append(f"${content}$")
                index = end + 1
                continue
            restored.append(markdown[index])
            index += 1
        return "".join(restored)

    def _unescape_markdown_math(self, text: str) -> str:
        return re.sub(r"\\([*_{}\[\]()#+\-.!])", r"\1", text)

    def _style_map(self, docx_bytes: bytes, user_style_map: str | None) -> str | None:
        generated = self._heading_style_map(docx_bytes)
        maps = [value for value in [generated, user_style_map] if value]
        return "\n".join(maps) if maps else None

    def _heading_style_map(self, docx_bytes: bytes) -> str | None:
        try:
            with ZipFile(io.BytesIO(docx_bytes)) as archive:
                styles = ET.fromstring(archive.read("word/styles.xml"))
                document = ET.fromstring(archive.read("word/document.xml"))
        except Exception:
            return None

        names: dict[str, str] = {}
        levels: dict[str, int] = {}
        for style in styles.findall(".//w:style", WORD_NS):
            if style.attrib.get(f"{{{WORD_NS['w']}}}type") != "paragraph":
                continue
            style_id = style.attrib.get(f"{{{WORD_NS['w']}}}styleId")
            if not style_id:
                continue
            name = style.find("w:name", WORD_NS)
            if name is not None:
                names[style_id] = name.attrib.get(f"{{{WORD_NS['w']}}}val", "")
            outline = style.find(".//w:outlineLvl", WORD_NS)
            if outline is not None:
                levels[style_id] = int(outline.attrib.get(f"{{{WORD_NS['w']}}}val", "0"))

        for paragraph in document.findall(".//w:body/w:p", WORD_NS):
            properties = paragraph.find("w:pPr", WORD_NS)
            if properties is None:
                continue
            style = properties.find("w:pStyle", WORD_NS)
            outline = properties.find("w:outlineLvl", WORD_NS)
            if style is None or outline is None:
                continue
            style_id = style.attrib.get(f"{{{WORD_NS['w']}}}val")
            if not style_id:
                continue
            level = int(outline.attrib.get(f"{{{WORD_NS['w']}}}val", "0"))
            levels[style_id] = min(level, levels.get(style_id, level))

        lines: list[str] = []
        for style_id, level in sorted(levels.items(), key=lambda item: item[1]):
            name = names.get(style_id, "")
            if not name or name.lower().startswith("toc"):
                continue
            heading_level = min(level + 1, 6)
            lines.append(
                f"p[style-name='{self._style_map_string(name)}'] => h{heading_level}:fresh"
            )
        return "\n".join(lines) or None

    def _style_map_string(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def _image_attributes(self, image: Any) -> dict[str, str]:
        if self.assets_dir is None:
            return {"src": ""}

        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self._image_index += 1
        self._emit_progress(
            stage="images",
            current=self._image_index,
            total=max(self._image_total, self._image_index),
            message=f"正在提取第 {self._image_index} / {max(self._image_total, self._image_index)} 张图片",
        )
        path = self._save_image_asset(image)
        return {"src": self._asset_markdown_path(path)}

    def _save_image_asset(self, image: Any) -> Path:
        with image.open() as image_stream:
            image_bytes = image_stream.read()

        if image.content_type in DISPLAYABLE_IMAGE_EXTENSIONS:
            extension = DISPLAYABLE_IMAGE_EXTENSIONS[image.content_type]
            path = self.assets_dir / f"image-{self._image_index:04d}{extension}"
            path.write_bytes(image_bytes)
            return path

        if image.content_type == "image/tiff":
            converted = self.assets_dir / f"image-{self._image_index:04d}.png"
            try:
                Image.open(io.BytesIO(image_bytes)).save(converted)
                return converted
            except Exception:
                pass

        extension = IMAGE_EXTENSIONS.get(image.content_type, ".bin")
        raw_path = self.assets_dir / f"image-{self._image_index:04d}{extension}"
        raw_path.write_bytes(image_bytes)

        placeholder = self.assets_dir / f"image-{self._image_index:04d}.png"
        self._save_unsupported_image_placeholder(placeholder, raw_path.name, image.content_type)
        return placeholder

    def _save_unsupported_image_placeholder(
        self,
        path: Path,
        original_name: str,
        content_type: str,
    ) -> None:
        canvas = Image.new("RGB", (1000, 300), "white")
        draw = ImageDraw.Draw(canvas)
        lines = [
            "Unsupported embedded image format",
            f"Format: {content_type or 'unknown'}",
            f"Original asset saved as: {original_name}",
        ]
        y = 70
        for line in lines:
            draw.text((60, y), line, fill=(40, 40, 40))
            y += 55
        draw.rectangle((20, 20, 980, 280), outline=(180, 180, 180), width=2)
        canvas.save(path)

    def _asset_markdown_path(self, path: Path) -> str:
        if self.assets_base_dir is None:
            return path.as_posix()
        try:
            import os

            return Path(os.path.relpath(path, self.assets_base_dir)).as_posix()
        except ValueError:
            return path.as_posix()

    def _count_images(self, docx_bytes: bytes) -> int:
        try:
            with ZipFile(io.BytesIO(docx_bytes)) as archive:
                return sum(
                    1
                    for name in archive.namelist()
                    if name.startswith("word/media/") and not name.endswith("/")
                )
        except Exception:
            return 0

    def _emit_progress(self, **event: Any) -> None:
        if self.progress_callback is not None:
            self.progress_callback(event)
