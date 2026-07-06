from __future__ import annotations

import io
from zipfile import ZipFile
from pathlib import Path
from typing import Any, BinaryIO
from xml.etree import ElementTree as ET

import mammoth
from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo
from markitdown.converter_utils.docx.pre_process import pre_process_docx
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


class EnhancedDocxConverter(DocumentConverter):
    def __init__(
        self,
        *,
        assets_dir: Path | None = None,
        assets_base_dir: Path | None = None,
    ) -> None:
        self.assets_dir = assets_dir
        self.assets_base_dir = assets_base_dir
        self._html_converter = HtmlConverter()
        self._image_index = 0

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
        style_map = self._style_map(docx_bytes, kwargs.get("style_map", None))
        pre_processed = pre_process_docx(io.BytesIO(docx_bytes))
        result = mammoth.convert_to_html(
            pre_processed,
            style_map=style_map,
            convert_image=mammoth.images.img_element(self._image_attributes),
        )
        return self._html_converter.convert_string(result.value, **kwargs)

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
        extension = IMAGE_EXTENSIONS.get(image.content_type, ".bin")
        path = self.assets_dir / f"image-{self._image_index:04d}{extension}"

        with image.open() as image_stream:
            path.write_bytes(image_stream.read())

        return {"src": self._asset_markdown_path(path)}

    def _asset_markdown_path(self, path: Path) -> str:
        if self.assets_base_dir is None:
            return path.as_posix()
        try:
            import os

            return Path(os.path.relpath(path, self.assets_base_dir)).as_posix()
        except ValueError:
            return path.as_posix()
