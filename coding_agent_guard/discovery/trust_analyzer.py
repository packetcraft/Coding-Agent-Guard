"""Probe: analyze trust configurations and detect high-risk settings."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

from coding_agent_guard.discovery import Finding, McpServer


def _home() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE", Path.home()))
    return Path.home()


def _load_json(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Finding ID counter ────────────────────────────────────────────────────────

class _Counter:
    def __init__(self, start: int = 1) -> None:
        self._n = start

    def next(self) -> str:
        fid = f"F-{self._n:03d}"
        self._n += 1
        return fid


# ── Gemini folder trust ───────────────────────────────────────────────────────

def _check_folder_trust(counter: _Counter) -> list[Finding]:
    findings: list[Finding] = []
    trusted_path = _home() / ".gemini" / "trustedFolders.json"
    if not trusted_path.exists():
        return findings

    data = _load_json(trusted_path)
    if not isinstance(data, dict):
        return findings

    for folder, trust_type in data.items():
        folder_p = Path(folder)
        # Heuristic: if the trusted path has no .git in it AND contains
        # multiple sub-dirs, it's a parent dir trust (overly broad).
        is_parent_dir = not (folder_p / ".git").exists() and folder_p.is_dir()
        if is_parent_dir:
            findings.append(Finding(
                id=counter.next(),
                category="OVERLY_BROAD_FOLDER_TRUST",
                severity="MEDIUM",
                agent="Gemini",
                source=str(trusted_path),
                detail=(
                    f"Parent directory '{folder}' trusted as {trust_type}. "
                    "All repos cloned into this directory inherit hook execution rights "
                    "without explicit per-repo approval."
                ),
                remediation=(
                    "Replace the parent-dir entry with individual repo entries in "
                    f"{trusted_path}"
                ),
            ))
    return findings


# ── Gemini orphaned hooks ─────────────────────────────────────────────────────

def _check_orphaned_hooks(counter: _Counter) -> list[Finding]:
    findings: list[Finding] = []
    hooks_path = _home() / ".gemini" / "trusted_hooks.json"
    if not hooks_path.exists():
        return findings

    data = _load_json(hooks_path)
    entries: list[str] = []
    if isinstance(data, list):
        entries = [str(e) for e in data]
    elif isinstance(data, dict):
        # Format: {"repo_path": ["name:command", ...], ...}
        for v in data.values():
            if isinstance(v, list):
                entries.extend(str(e) for e in v)
            elif isinstance(v, str):
                entries.append(v)

    for entry in entries:
        # Entry may be "name:command" or just "command"
        if ":" in entry:
            cmd = entry.split(":", 1)[1].strip()
        else:
            cmd = entry.strip()

        # Extract the binary name (first token)
        binary = cmd.split()[0] if cmd else ""
        if binary and not shutil.which(binary) and not Path(binary).exists():
            findings.append(Finding(
                id=counter.next(),
                category="ORPHANED_HOOK",
                severity="LOW",
                agent="Gemini",
                source=str(hooks_path),
                detail=(
                    f"Trusted hook '{entry}' has a command that cannot be resolved: '{binary}'. "
                    "Stale approval — the binary no longer exists at that path."
                ),
                remediation=(
                    f"Remove the stale entry from {hooks_path} or reinstall the hook binary."
                ),
            ))
    return findings


# ── API key exposure ──────────────────────────────────────────────────────────

_ENV_KEY_PATTERNS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "COHERE_API_KEY",
    "MISTRAL_API_KEY",
]

_DOTENV_PATTERN = re.compile(
    r"^(ANTHROPIC_API_KEY|OPENAI_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|"
    r"COHERE_API_KEY|MISTRAL_API_KEY)\s*=\s*.+",
    re.MULTILINE,
)


def _check_api_keys_env(counter: _Counter) -> list[Finding]:
    findings: list[Finding] = []
    exposed: list[str] = [k for k in _ENV_KEY_PATTERNS if os.environ.get(k)]
    if exposed:
        findings.append(Finding(
            id=counter.next(),
            category="API_KEY_IN_ENV",
            severity="MEDIUM",
            agent=None,
            source="environment variables",
            detail=(
                f"AI API key(s) found in environment: {', '.join(exposed)}. "
                "Keys in the process environment are readable by any child process "
                "spawned by the shell, including AI agents."
            ),
            remediation=(
                "Use a secrets manager or per-project .env files (gitignored) "
                "rather than exporting keys in shell profile files."
            ),
        ))
    return findings


def _check_api_keys_files(scan_root: str, counter: _Counter) -> list[Finding]:
    findings: list[Finding] = []
    root = Path(scan_root).expanduser().resolve()

    dotenv_files: list[Path] = []

    def _walk(p: Path, depth: int) -> None:
        if depth > 4:
            return
        for name in (".env", ".env.local", ".env.development", ".env.production"):
            candidate = p / name
            if candidate.exists() and candidate.is_file():
                dotenv_files.append(candidate)
        try:
            for child in sorted(p.iterdir()):
                if child.is_dir() and not child.name.startswith(".") and child.name != "node_modules":
                    _walk(child, depth + 1)
        except PermissionError:
            pass

    _walk(root, 0)

    for env_file in dotenv_files:
        try:
            text = env_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matches = _DOTENV_PATTERN.findall(text)
        if matches:
            findings.append(Finding(
                id=counter.next(),
                category="API_KEY_IN_FILE",
                severity="MEDIUM",
                agent=None,
                source=str(env_file),
                detail=(
                    f"AI API key(s) found in file: {', '.join(matches)}. "
                    "Ensure this file is in .gitignore and not committed to source control."
                ),
                remediation=(
                    "Add to .gitignore. Rotate the key if it may have been committed. "
                    "Use a secrets manager for CI/CD."
                ),
            ))
    return findings


# ── Remote MCP trust=true findings ───────────────────────────────────────────

def _check_remote_mcp_trust(mcp_servers: list[McpServer], counter: _Counter) -> list[Finding]:
    findings: list[Finding] = []
    for s in mcp_servers:
        if s.transport == "remote" and s.trust:
            findings.append(Finding(
                id=counter.next(),
                category="REMOTE_MCP_TRUST_TRUE",
                severity="HIGH",
                agent=s.agent,
                source=s.source,
                detail=(
                    f"Remote MCP server '{s.name}' ({s.url}) is configured with trust=true. "
                    "The agent will auto-connect without prompting the user. "
                    "Tools exposed by this server are not yet enumerated."
                ),
                remediation=(
                    "Remove 'trust: true' or set it to false to require explicit approval. "
                    "Run with --enumerate-mcp (Phase 4) to audit exposed tools."
                ),
            ))
    return findings


# ── Unguarded repo findings ───────────────────────────────────────────────────

def _check_unguarded_repos(gap_results: list, counter: _Counter) -> list[Finding]:
    """Import GapResult type inline to avoid circular import at module level."""
    findings: list[Finding] = []
    for g in gap_results:
        if g.status == "UNGUARDED":
            findings.append(Finding(
                id=counter.next(),
                category="UNGUARDED_AGENT",
                severity="MEDIUM",
                agent=g.agent,
                source=g.repo_path,
                detail=(
                    f"{g.agent} agent active but no guard hook registered in '{g.repo_path}'. "
                    "Tool calls in this repo bypass Coding Agent Guard entirely."
                ),
                remediation=f'Run: python install_hooks.py "{g.repo_path}"',
            ))

        elif g.status == "SHADOW_HOOK":
            findings.append(Finding(
                id=counter.next(),
                category="SHADOW_HOOK",
                severity="LOW",
                agent=g.agent,
                source=g.repo_path,
                detail=(
                    f"{g.agent} has a hook in '{g.repo_path}' but it is not Coding Agent Guard: "
                    f"'{g.hook_command}'. Unknown tool is intercepting agent calls."
                ),
                remediation=(
                    "Verify the hook command is intentional. "
                    "If not, replace with Coding Agent Guard."
                ),
            ))
        elif g.status == "ARTIFACT_ONLY":
            findings.append(Finding(
                id=counter.next(),
                category="PASSIVE_MONITORING_ACTIVE",
                severity="INFO",
                agent=g.agent,
                source=g.repo_path,
                detail=(
                    f"Artifact-based agent '{g.agent}' detected. Active artifacts found: "
                    f"{', '.join(g.artifact_files)}. The guard is passively monitoring "
                    "agent state changes but NOT intercepting individual tool calls."
                ),
                remediation=(
                    "For full enforcement, wrap the agent command with 'shell_guard'. "
                    "This enables active Action Guard and Injection Guard primitives."
                ),
            ))
        elif g.status == "EXTERNAL_BRAIN":
            findings.append(Finding(
                id=counter.next(),
                category="SHADOW_AI_EXTERNAL_BRAIN",
                severity="INFO",
                agent=g.agent,
                source=f"Brain Session: {g.external_brain_session}",
                detail=(
                    f"Active Antigravity brain session '{g.external_brain_session}' detected "
                    "for this workspace via home directory audit. No artifacts found in project repo. "
                    "This indicates passive monitoring via 'Digital Exhaust'."
                ),
                remediation=(
                    "Clean up home directory brain storage if you wish to completely remove "
                    "agent traces, or install a hook for active enforcement."
                ),
            ))
    return findings





# ── Public API ────────────────────────────────────────────────────────────────

def analyze(
    scan_root: str,
    mcp_servers: list[McpServer],
    gap_results: list,
    finding_start: int = 1,
) -> list[Finding]:
    """Run all trust/posture checks and return a list of findings."""
    counter = _Counter(finding_start)
    findings: list[Finding] = []
    findings.extend(_check_folder_trust(counter))
    findings.extend(_check_orphaned_hooks(counter))
    findings.extend(_check_api_keys_env(counter))
    findings.extend(_check_api_keys_files(scan_root, counter))
    findings.extend(_check_remote_mcp_trust(mcp_servers, counter))
    findings.extend(_check_unguarded_repos(gap_results, counter))
    return findings
