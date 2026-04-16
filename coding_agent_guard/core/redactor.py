import re
import json

# Each entry: (compiled_pattern, replacement_token)
# Applied in order; all patterns run (not first-match) to catch overlapping secrets.
_REDACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"),                                           "[REDACTED:api_key]"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"),                                            "[REDACTED:github_pat]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"),                                               "[REDACTED:aws_key]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.~+/]{20,}"),                          "[REDACTED:bearer_token]"),
    (re.compile(r"-----BEGIN [A-Z ]+-----[\s\S]+?-----END [A-Z ]+-----"),           "[REDACTED:pem_block]"),
    (re.compile(r"(?i)(secret|password|passwd|token|api_key)\s*[=:]\s*\S{16,}"),   "[REDACTED:credential]"),
]


def redact(text: str) -> tuple[str, int]:
    """Return ``(redacted_text, substitution_count)``."""
    count = 0
    for pattern, replacement in _REDACTION_PATTERNS:
        text, n = pattern.subn(replacement, text)
        count += n
    return text, count


def redact_dict(d: dict) -> tuple[dict, int]:
    """Redact secrets inside a dict by round-tripping through JSON."""
    raw = json.dumps(d)
    redacted_raw, count = redact(raw)
    try:
        return json.loads(redacted_raw), count
    except json.JSONDecodeError:
        return d, count  # Redaction broke JSON structure — return original
