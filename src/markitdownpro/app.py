from __future__ import annotations

from pathlib import Path
from typing import Any

from .cache import configure_project_cache


configure_project_cache()

from markitdown import MarkItDown

from .pdf_converter import EnhancedPdfConverter


class MarkItDownPro:
    def __init__(
        self,
        *,
        pdf_mode: str = "academic",
        formula_ocr: bool = False,
        assets_dir: str | Path | None = None,
        assets_base_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        configure_project_cache()
        self._markitdown = MarkItDown(**kwargs)
        self._markitdown.register_converter(
            EnhancedPdfConverter(
                mode=pdf_mode,
                formula_ocr=formula_ocr,
                assets_dir=Path(assets_dir) if assets_dir is not None else None,
                assets_base_dir=Path(assets_base_dir)
                if assets_base_dir is not None
                else None,
            ),
            priority=-1.0,
        )

    def convert(self, source: Any, **kwargs: Any):
        return self._markitdown.convert(source, **kwargs)
