import re

# Detection only -- never modifies the text or blocks ingestion. A flagged postmortem
# still gets chunked, embedded, and indexed; `injection_flagged` is a signal for a
# human/UI, and later phases' agent prompts are what actually treat retrieved content
# as untrusted data regardless of this flag.
_INSTRUCTION_PHRASES = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore the above",
    "disregard the above",
    "disregard previous instructions",
    "you are now",
    "new instructions:",
]

# Zero-width space, zero-width non-joiner, zero-width joiner, byte-order mark --
# written as escapes, not literal characters, so they survive any editor/encoding
# round-trip intact rather than silently disappearing or mutating.
_ZERO_WIDTH_CHARS = "​‌‍﻿"

_HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)


def screen(text: str) -> bool:
    lowered = text.lower()
    if any(phrase in lowered for phrase in _INSTRUCTION_PHRASES):
        return True
    if any(char in text for char in _ZERO_WIDTH_CHARS):
        return True
    return bool(_HTML_COMMENT_PATTERN.search(text))
