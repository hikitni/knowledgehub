from __future__ import annotations

import re
from pathlib import Path

SENSITIVE_PATH_PARTS = {
    ".env",
    ".git",
    "node_modules",
    "target",
    "build",
    "dist",
    "logs",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".jks"}
KEYWORDS = ("password", "passwd", "token", "secret", "credential", "private key")
PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    (
        "credential-field",
        re.compile(r"(?i)\b(password|passwd|secret|access[_-]?token|api[_-]?key)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
    ),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
)


def reject_path(path: Path) -> str | None:
    lower_parts = [part.lower() for part in path.parts]
    if any(part in SENSITIVE_PATH_PARTS for part in lower_parts):
        return "sensitive-path"
    name = path.name.lower()
    if name.startswith(".env"):
        return "environment-file"
    if path.suffix.lower() in SENSITIVE_SUFFIXES:
        return "credential-file"
    if "secret" in name or "credential" in name:
        return "sensitive-name"
    if path.suffix.lower() == ".log":
        return "log-file"
    return None


def detect_sensitive_content(text: str, max_bytes: int) -> str | None:
    # Bound work before regex matching; keep the beginning and end where credentials
    # and exported environment blocks most commonly occur.
    encoded = text.encode("utf-8", errors="ignore")
    if len(encoded) > max_bytes:
        half = max_bytes // 2
        sample = (encoded[:half] + b"\n" + encoded[-half:]).decode("utf-8", errors="ignore")
    else:
        sample = text
    lower = sample.lower()
    if not any(keyword in lower for keyword in KEYWORDS) and "akia" not in lower and "asia" not in lower:
        return None
    for name, pattern in PATTERNS:
        if pattern.search(sample):
            return name
    return None
