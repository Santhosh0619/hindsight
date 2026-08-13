import re

from pydantic import BaseModel

# Markdown headings ("## Root Cause") or plain postmortem section labels ("Root Cause:")
# on their own line.
_SECTION_HEADING_PATTERN = re.compile(
    r"^(?:#{1,6}\s+.+|(?:Summary|Timeline|Root Causes?|Impact|Action Items?|Detection|"
    r"Remediation):?\s*)$",
    re.IGNORECASE | re.MULTILINE,
)

_MAX_CHUNK_CHARS = 1200
_CHUNK_OVERLAP_CHARS = 150


class ChunkSpan(BaseModel):
    section_label: str | None
    content: str
    char_start: int
    char_end: int


def chunk(text: str) -> list[ChunkSpan]:
    spans: list[ChunkSpan] = []
    for label, section_text, section_start in _split_into_sections(text):
        spans.extend(_size_split(label, section_text, section_start))
    return spans


def _split_into_sections(text: str) -> list[tuple[str | None, str, int]]:
    matches = list(_SECTION_HEADING_PATTERN.finditer(text))
    if not matches:
        return [(None, text, 0)] if text.strip() else []

    sections: list[tuple[str | None, str, int]] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()]
        if preamble.strip():
            sections.append((None, preamble, 0))

    for i, match in enumerate(matches):
        label = match.group(0).strip().lstrip("#").strip().rstrip(":").strip()
        content_start = match.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[content_start:content_end]
        if section_text.strip():
            sections.append((label, section_text, content_start))
    return sections


def _size_split(label: str | None, text: str, base_offset: int) -> list[ChunkSpan]:
    if not text.strip():
        return []
    if len(text) <= _MAX_CHUNK_CHARS:
        stripped = text.strip()
        local_offset = text.index(stripped)
        start = base_offset + local_offset
        return [
            ChunkSpan(
                section_label=label,
                content=stripped,
                char_start=start,
                char_end=start + len(stripped),
            )
        ]

    spans: list[ChunkSpan] = []
    step = _MAX_CHUNK_CHARS - _CHUNK_OVERLAP_CHARS
    pos = 0
    n = len(text)
    while pos < n:
        end = min(pos + _MAX_CHUNK_CHARS, n)
        window = text[pos:end]
        window_stripped = window.strip()
        if window_stripped:
            local_offset = window.index(window_stripped)
            start = base_offset + pos + local_offset
            spans.append(
                ChunkSpan(
                    section_label=label,
                    content=window_stripped,
                    char_start=start,
                    char_end=start + len(window_stripped),
                )
            )
        if end == n:
            break
        pos += step
    return spans
