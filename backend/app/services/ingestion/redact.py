import re

# Order matters: connection strings and bearer tokens are matched before the plain
# email/IP patterns, which would otherwise partially consume a "user:pass@host"
# substring (the email pattern happily matches "pass@db.example.com" on its own) and
# leave the rest of the credential unredacted.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\w+://[^\s:/@]+:[^\s:/@]+@[^\s/]+"), "[REDACTED_CONNECTION_STRING]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{8,}=*"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
]


def redact(text: str) -> str:
    redacted = text
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
