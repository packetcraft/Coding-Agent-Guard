import re

# Shell composition characters that disqualify a command from allowlisting
# regardless of prefix match. Piped or redirected commands change safety profile.
# Includes pipes, redirections, command substitution, and process substitution.
# Added \n to prevent newline bypasses.
_SHELL_COMPOSITION = re.compile(r"[|><&;\n`]|\$\(")

_BUILTIN_ALLOWLIST: list[re.Pattern] = [
    re.compile(r"^git\s+(log|status|diff|show|branch|remote|tag|describe|rev-parse|ls-files)(\s|$)"),
    re.compile(r"^(cat|head|tail|wc|file|stat)\s"),
    re.compile(r"^ls(\s|$)"),
    re.compile(r"^pwd$"),
    re.compile(r"^(python|pip|node|npm|cargo|go|rustc)\s+(--version|-V|list\b)"),
    re.compile(r"^echo\s+[^>|&;`$]*$"),
]


def is_allowlisted(command: str, extra_patterns: list[str]) -> bool:
    """Return True only if the command is read-only and contains no shell composition."""
    if _SHELL_COMPOSITION.search(command):
        return False
    all_patterns = _BUILTIN_ALLOWLIST + [re.compile(p) for p in extra_patterns]
    return any(p.search(command) for p in all_patterns)
