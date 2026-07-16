from __future__ import annotations

import re
from collections.abc import Iterable

from .models import Chunk

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _split_large(text: str, start_line: int, max_chars: int, overlap: int) -> Iterable[tuple[str, int, int]]:
    if len(text) <= max_chars:
        yield text, start_line, start_line + max(0, text.count("\n"))
        return
    cursor = 0
    while cursor < len(text):
        target = min(len(text), cursor + max_chars)
        end = target
        if target < len(text):
            candidates = [text.rfind("\n\n", cursor, target), text.rfind("\n", cursor, target)]
            end = max(candidates)
            if end <= cursor + max_chars // 2:
                end = target
        piece = text[cursor:end].strip()
        before = text[:cursor]
        piece_start = start_line + before.count("\n")
        if piece:
            yield piece, piece_start, piece_start + piece.count("\n")
        if end >= len(text):
            break
        cursor = max(cursor + 1, end - overlap)


def chunk_document(content: str, file_type: str, max_chars: int = 6000, overlap: int = 300) -> list[Chunk]:
    lines = content.splitlines()
    sections: list[tuple[str | None, str | None, int, list[str]]] = []
    heading_stack: list[str] = []
    current_heading: str | None = None
    current_path: str | None = None
    current_start = 1
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            sections.append((current_heading, current_path, current_start, current_lines))
            current_lines = []

    if file_type in {"md", "markdown"}:
        for line_no, line in enumerate(lines, start=1):
            match = HEADING_RE.match(line)
            if match:
                flush()
                level = len(match.group(1))
                title = match.group(2).strip()
                heading_stack[:] = heading_stack[: level - 1]
                while len(heading_stack) < level - 1:
                    heading_stack.append("")
                heading_stack.append(title)
                current_heading = title
                current_path = " / ".join(item for item in heading_stack if item)
                current_start = line_no
                current_lines = [line]
            else:
                if not current_lines:
                    current_start = line_no
                current_lines.append(line)
        flush()
    else:
        sections.append((None, None, 1, lines))

    if not sections and content:
        sections.append((None, None, 1, lines))

    chunks: list[Chunk] = []
    ordinal = 0
    for heading, heading_path, start, section_lines in sections:
        section_text = "\n".join(section_lines).strip()
        if not section_text:
            continue
        for piece, piece_start, piece_end in _split_large(section_text, start, max_chars, overlap):
            chunks.append(
                Chunk(
                    ordinal=ordinal,
                    heading=heading,
                    heading_path=heading_path,
                    content=piece,
                    start_line=piece_start,
                    end_line=piece_end,
                )
            )
            ordinal += 1
    return chunks
