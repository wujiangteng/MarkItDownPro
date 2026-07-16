from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pdf2zh.translator import BingTranslator, GoogleTranslator


SUPPORTED_TRANSLATION_SERVICES = ("google", "bing")
DEFAULT_LANG_IN = "en"
DEFAULT_LANG_OUT = "zh"


@dataclass(frozen=True)
class TranslationResult:
    text: str


class TextTranslator:
    def __init__(
        self,
        *,
        service: str = "google",
        lang_in: str = DEFAULT_LANG_IN,
        lang_out: str = DEFAULT_LANG_OUT,
    ) -> None:
        if service not in SUPPORTED_TRANSLATION_SERVICES:
            supported = ", ".join(SUPPORTED_TRANSLATION_SERVICES)
            raise ValueError(
                f"Unsupported translation service: {service}. Use one of: {supported}"
            )

        translator_type = {
            "google": GoogleTranslator,
            "bing": BingTranslator,
        }[service]
        self.service = service
        self._translator = translator_type(lang_in, lang_out, None)
        self._chunk_limit = 4500 if service == "google" else 900

    def translate_markdown(
        self,
        markdown: str,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> TranslationResult:
        blocks = list(_iter_markdown_blocks(markdown))
        translatable_total = sum(1 for block in blocks if block.translatable)
        translated_count = 0
        output: list[str] = []

        for block in blocks:
            if not block.translatable:
                output.append(block.text)
                continue

            translated_count += 1
            if progress_callback is not None:
                progress_callback(
                    {
                        "stage": "translation",
                        "current": translated_count,
                        "total": translatable_total,
                        "message": f"正在翻译第 {translated_count} / {translatable_total} 段",
                    }
                )
            output.append(self._translate_block(block.text))

        return TranslationResult(text="".join(output))

    def _translate_block(self, text: str) -> str:
        newline = ""
        body = text
        if body.endswith("\n"):
            newline = "\n"
            body = body[:-1]

        prefix, content = _split_markdown_prefix(body)
        if not content.strip():
            return text

        protected, placeholders = _protect_markdown_spans(content)
        translated = " ".join(
            self._translator.translate(chunk)
            for chunk in _split_chunks(protected, self._chunk_limit)
        )
        translated = _restore_markdown_spans(translated, placeholders)
        return f"{prefix}{translated}{newline}"


@dataclass(frozen=True)
class _MarkdownBlock:
    text: str
    translatable: bool


def _iter_markdown_blocks(markdown: str):
    lines = markdown.splitlines(keepends=True)
    paragraph: list[str] = []
    in_fence = False
    in_math = False

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            text = "".join(paragraph)
            paragraph = []
            return _MarkdownBlock(text, _is_translatable_block(text))
        return None

    for line in lines:
        if line.lstrip().startswith("```"):
            block = flush_paragraph()
            if block is not None:
                yield block
            in_fence = not in_fence
            yield _MarkdownBlock(line, False)
            continue

        if line.strip().startswith("$$"):
            block = flush_paragraph()
            if block is not None:
                yield block
            if line.count("$$") % 2 == 1:
                in_math = not in_math
            yield _MarkdownBlock(line, False)
            continue

        if in_fence or not line.strip():
            block = flush_paragraph()
            if block is not None:
                yield block
            yield _MarkdownBlock(line, False)
            continue

        if in_math:
            yield _MarkdownBlock(line, False)
            continue

        if _is_structural_line(line):
            block = flush_paragraph()
            if block is not None:
                yield block
            yield _MarkdownBlock(line, False)
            continue

        paragraph.append(line)

    block = flush_paragraph()
    if block is not None:
        yield block


def _is_structural_line(line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith("<!--")
        or stripped.startswith("![")
        or stripped.startswith("<")
        or stripped.startswith("|")
        or re.match(r"^[-*_]{3,}$", stripped) is not None
    )


def _is_translatable_block(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return re.search(r"[A-Za-z]", stripped) is not None


def _split_markdown_prefix(text: str) -> tuple[str, str]:
    match = re.match(
        r"^(\s*(?:#{1,6}\s+|>\s+|[-*+]\s+|\d+[.)]\s+)?)(.*)$",
        text,
        re.S,
    )
    if match is None:
        return "", text
    return match.group(1), match.group(2)


def _split_chunks(text: str, limit: int) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return [text]

    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current} {part}".strip() if current else part
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(part) > limit:
            chunks.append(part[:limit])
            part = part[limit:]
        current = part
    if current:
        chunks.append(current)
    return chunks


def _protect_markdown_spans(text: str) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}

    patterns = [
        r"!\[[^\]]*\]\([^)]+\)",
        r"\[[^\]]+\]\([^)]+\)",
        r"`[^`]+`",
        r"\$\$.*?\$\$",
        r"(?<!\\)\$(?!\$).*?(?<!\\)\$",
        r"<[^>]+>",
    ]

    protected = text
    for pattern in patterns:
        protected = re.sub(
            pattern,
            lambda match: _store_placeholder(match.group(0), placeholders),
            protected,
            flags=re.S,
        )
    return protected, placeholders


def _store_placeholder(value: str, placeholders: dict[str, str]) -> str:
    placeholder = f"{{v{len(placeholders)}}}"
    placeholders[placeholder] = value
    return placeholder


def _restore_markdown_spans(text: str, placeholders: dict[str, str]) -> str:
    restored = text
    for placeholder, value in placeholders.items():
        restored = re.sub(re.escape(placeholder), value, restored, flags=re.I)
        spaced = r"\{\s*" + re.escape(placeholder[1:-1]) + r"\s*\}"
        restored = re.sub(spaced, value, restored, flags=re.I)
    return restored
