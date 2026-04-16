import pytest
from coding_agent_guard.core.redactor import redact
from coding_agent_guard.core.allowlist import is_allowlisted

def test_secret_redaction():
    text = "My key is sk-123456789012345678901234"
    redacted, count = redact(text)
    assert "[REDACTED:api_key]" in redacted
    assert count == 1

def test_allowlist_git():
    assert is_allowlisted("git status", []) is True
    assert is_allowlisted("git log -n 5", []) is True

def test_allowlist_destructive_block():
    # Should be False because of shell composition or not in allowlist
    assert is_allowlisted("rm -rf /", []) is False
    assert is_allowlisted("ls | grep secret", []) is False

def test_allowlist_custom_patterns():
    assert is_allowlisted("my-custom-cmd", ["^my-custom-cmd$"]) is True
