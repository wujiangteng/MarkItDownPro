from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .cache import configure_project_cache


configure_project_cache()

from markitdown import MarkItDown

from .docx_converter import EnhancedDocxConverter
from .pdf_converter import EnhancedPdfConverter


class MarkItDownPro:
    def __init__(
        self,
        *,
        pdf_mode: str = "academic",
        formula_ocr: bool = False,
        assets_dir: str | Path | None = None,
        assets_base_dir: str | Path | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        **kwargs: Any,
    ) -> None:
        configure_project_cache()
        self._markitdown = MarkItDown(**kwargs)
        self._markitdown.register_converter(
            EnhancedDocxConverter(
                assets_dir=Path(assets_dir) if assets_dir is not None else None,
                assets_base_dir=Path(assets_base_dir)
                if assets_base_dir is not None
                else None,
                progress_callback=progress_callback,
            ),
            priority=-1.0,
        )
        self._markitdown.register_converter(
            EnhancedPdfConverter(
                mode=pdf_mode,
                formula_ocr=formula_ocr,
                assets_dir=Path(assets_dir) if assets_dir is not None else None,
                assets_base_dir=Path(assets_base_dir)
                if assets_base_dir is not None
                else None,
                progress_callback=progress_callback,
            ),
            priority=-1.0,
        )

    def convert(self, source: Any, **kwargs: Any):
        return self._markitdown.convert(source, **kwargs)
