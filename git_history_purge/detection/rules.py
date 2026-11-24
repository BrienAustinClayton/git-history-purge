"""What counts as a secret value: key and URL patterns, placeholders, common words and local URLs."""

import re

ASSIGNMENT_PATTERN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.*?)\s*$")
URL_PASSWORD_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^:/@\s]+:([^@\s]+)@([^/:?\s]+)")
GITLEAKS_KEY_PATTERN = re.compile(r"^\s*(?:export\s+)?[\"']?([A-Za-z_][A-Za-z0-9_]{1,60})[\"']?\s*[:=]")
ENV_STYLE_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]+$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "postgres", "db", "host.docker.internal"}
COMMON_NON_SECRET_VALUES = {
    "postgres", "postgresql", "password", "localhost", "changeme", "development",
    "production", "undefined", "null", "true", "false", "secret", "example",
}
PLACEHOLDER_PATTERNS = [
    re.compile(r"^<.*>$"),
    re.compile(r"^\$\{.*\}$"),
    re.compile(r"^\$\(.*\)$"),
    re.compile(r"^\{\{.*\}\}$"),
    re.compile(r"(your[_-]|xxxx|change[_-]?me|placeholder|REMOVED AT|\*\*\*REMOVED|SECRET REMOVED)", re.IGNORECASE),
]
INCLUDED = "included"


def strip_quotes_and_comment(raw_value: str) -> str:
    is_quoted = len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in "\"'"
    if is_quoted:
        return raw_value[1:-1]
    return raw_value.split(" #", 1)[0].strip()


def classify_value(value: str, min_length: int) -> str:
    url_match = URL_PASSWORD_PATTERN.match(value)
    is_too_short = len(value) < min_length
    is_placeholder = any(pattern.search(value) for pattern in PLACEHOLDER_PATTERNS)
    is_common_word = value.lower() in COMMON_NON_SECRET_VALUES
    is_plain_lowercase_word = value.isalpha() and value.islower() and len(value) < 16
    cannot_be_replace_text_literal = "==>" in value or "\n" in value or "\r" in value
    is_local_url = url_match is not None and url_match.group(2) in LOCAL_HOSTS

    if is_too_short:
        return "skipped: shorter than minimum length"
    if is_placeholder:
        return "skipped: placeholder"
    if is_common_word or is_plain_lowercase_word:
        return "skipped: common word"
    if cannot_be_replace_text_literal:
        return "skipped: cannot be a replace-text literal"
    if is_local_url:
        return "skipped: local development URL"
    return INCLUDED
