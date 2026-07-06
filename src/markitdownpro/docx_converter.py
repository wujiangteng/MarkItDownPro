from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO

import mammoth
from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo
from markitdown.converter_utils.docx.pre_process import pre_process_docx
from markitdown.converters._html_converter import HtmlConverter


DOCX_EXTENSIONS = {".docx"}
DOCX_MIME_PREFIXES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)

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
        style_map = kwargs.get("style_map", None)
        pre_processed = pre_process_docx(file_stream)
        result = mammoth.convert_to_html(
            pre_processed,
            style_map=style_map,
            convert_image=mammoth.images.img_element(self._image_attributes),
        )
        return self._html_converter.convert_string(result.value, **kwargs)

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
