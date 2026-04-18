"""Probe: walk filesystem for all agent config files and resolve hook inheritance."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from coding_agent_guard.discovery import HookEntry, RepoConfig


# Patterns that identify a hook command as the guard itself
_GUARD_PATTERNS = [
    "coding-agent-guard",
    "agentic_guard",
    "agentic-guard",
]


def _is_guard_command(command: str) -> bool:
    cmd_lower = command.lower().replace("\\", "/")
    return any(p in cmd_lower for p in _GUARD_PATTERNS)


def _home() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE", Path.home()))
    return Path.home()


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Claude config parsing ─────────────────────────────────────────────────────

def _parse_claude_hooks(settings: dict, event: str) -> list[HookEntry]:
    """Parse PreToolUse / PostToolUse hook entries from a Claude settings dict."""
    entries: list[HookEntry] = []
    hooks_section = settings.get("hooks", {})
    event_hooks = hooks_section.get(event, [])
    for item in event_hooks:
        matcher = item.get("matcher", ".*")
        for h in item.get("hooks", []):
            cmd = h.get("command", "")
            entries.append(HookEntry(
                event=event,
                matcher=matcher,
                command=cmd,
                is_guard=_is_guard_command(cmd),
            ))
    return entries


def _claude_hooks_from_settings(settings: dict) -> list[HookEntry]:
    entries = []
    for event in ("PreToolUse", "PostToolUse"):
        entries.extend(_parse_claude_hooks(settings, event))
    return entries


# ── Gemini config parsing ─────────────────────────────────────────────────────

def _parse_gemini_hooks(settings: dict, event: str) -> list[HookEntry]:
    entries: list[HookEntry] = []
    hooks_section = settings.get("hooks", {})
    event_hooks = hooks_section.get(event, [])
    for item in event_hooks:
        matcher = item.get("matcher", ".*")
        for h in item.get("hooks", []):
            cmd = h.get("command", "")
            entries.append(HookEntry(
                event=event,
                matcher=matcher,
                command=cmd,
                is_guard=_is_guard_command(cmd),
            ))
    return entries


def _gemini_hooks_from_settings(settings: dict) -> list[HookEntry]:
    entries = []
    for event in ("BeforeTool", "AfterTool"):
        entries.extend(_parse_gemini_hooks(settings, event))
    return entries


def _gemini_mcp_count(settings: dict) -> int:
    return len(settings.get("mcpServers", {}))


def _claude_mcp_count(settings: dict) -> int:
    return len(settings.get("mcpServers", {}))


# ── Global config locations ───────────────────────────────────────────────────

def _global_claude_settings_paths() -> list[Path]:
    return [_home() / ".claude" / "settings.json",
            _home() / ".claude" / "settings.local.json"]


def _global_gemini_settings_paths() -> list[Path]:
    return [_home() / ".gemini" / "settings.json"]


# ── Repo scanning ─────────────────────────────────────────────────────────────

def _is_repo(path: Path) -> bool:
    """Heuristic: a directory is a 'repo' if it contains .git, or at minimum a
    recognised agent config dir or instructions file."""
    return (
        (path / ".git").exists() or 
        (path / ".claude").exists() or 
        (path / ".gemini").exists() or
        (path / ".zed").exists() or
        (path / ".agents").exists() or
        (path / "AGENTS.md").exists() or
        (path / "implementation_plan.md").exists() or
        (path / "task.md").exists() or
        (path / "walkthrough.md").exists()
    )


def _find_repos(scan_root: Path, max_depth: int = 4) -> list[Path]:
    """Walk scan_root up to max_depth and collect repo directories."""
    repos: list[Path] = []

    def _walk(p: Path, depth: int) -> None:
        if depth > max_depth:
            return
        if _is_repo(p) and p != scan_root:
            repos.append(p)
            return  # don't recurse into nested repos
        try:
            for child in sorted(p.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    _walk(child, depth + 1)
        except PermissionError:
            pass

    _walk(scan_root, 0)
    return repos


def _parent_config(repo: Path, filename: str) -> tuple[dict, str | None]:
    """
    Walk from repo's parent upward to find an inherited config file.
    Returns (settings_dict, config_path_str) or ({}, None).
    """
    current = repo.parent
    for _ in range(6):  # cap at 6 levels up
        candidate = current / filename
        if candidate.exists():
            return _load_json(candidate), str(candidate)
        if current.parent == current:
            break
        current = current.parent
    return {}, None


# Regex for file:/// URIs
_URI_PATTERN = re.compile(r"file:///([a-zA-Z]:/[^ \n`\"'>]+|/[^ \n`\"'>]+)")


def _probe_antigravity_brain() -> list[RepoConfig]:
    """
    Search the local Antigravity brain directory for session artifacts
    that contain workspace file paths.
    """
    roots = [
        _home() / ".gemini" / "antigravity" / "brain",
    ]
    if sys.platform == "darwin":
        roots.append(_home() / "Library" / "Application Support" / "Antigravity" / "brain")

    configs: list[RepoConfig] = []
    # Key = normalized repo path, Value = RepoConfig
    discovered: dict[str, RepoConfig] = {}

    for brain_root in roots:
        if not brain_root.exists():
            continue

        try:
            for sess_dir in brain_root.iterdir():
                if not sess_dir.is_dir():
                    continue
                
                # Look for recent artifacts
                # Note: implementation_plan.md and walkthrough.md usually contain URIs
                for art_name in ["implementation_plan.md", "walkthrough.md"]:
                    art_file = sess_dir / art_name
                    if not art_file.exists():
                        continue
                    
                    try:
                        content = art_file.read_text(encoding="utf-8", errors="replace")
                        matches = _URI_PATTERN.findall(content)
                        for path in matches:
                            # Normalize path: convert to absolute
                            norm_path = path.replace("\\", "/").rstrip("/")
                            
                            p = Path(norm_path)
                            repo_root = None
                            
                            # Walk up to find repo root
                            current = p if p.is_dir() else p.parent
                            for _ in range(5):
                                if (current / ".git").exists() or (current / ".claude").exists() or (current / ".gemini").exists():
                                    repo_root = current
                                    break
                                if current.parent == current:
                                    break
                                current = current.parent
                            
                            if not repo_root:
                                continue

                            repo_str = str(repo_root.resolve())
                            if repo_str not in discovered:
                                discovered[repo_str] = RepoConfig(
                                    repo_path=repo_str,
                                    agent="Antigravity (Brain Session)",
                                    config_path=str(art_file),
                                    external_brain_session=sess_dir.name
                                )
                    except Exception:
                        continue
        except Exception:
            pass

    return list(discovered.values())



# ── Public API ────────────────────────────────────────────────────────────────

def crawl(scan_root: str) -> list[RepoConfig]:
    """
    Crawl scan_root for all Claude and Gemini config files.
    Returns a RepoConfig for every (repo × agent) pair found, including
    repos that inherit hooks from a parent-dir global config.
    """
    root = Path(scan_root).expanduser().resolve()
    repos = _find_repos(root)

    # Also include scan_root itself if it has agent configs
    if _is_repo(root):
        repos.insert(0, root)

    configs: list[RepoConfig] = []

    # Build global hook lists once
    global_claude_hooks: list[HookEntry] = []
    global_claude_cfg_path: str | None = None
    for gp in _global_claude_settings_paths():
        if gp.exists():
            s = _load_json(gp)
            hooks = _claude_hooks_from_settings(s)
            if hooks:
                global_claude_hooks = hooks
                global_claude_cfg_path = str(gp)
                break

    global_gemini_hooks: list[HookEntry] = []
    global_gemini_cfg_path: str | None = None
    for gp in _global_gemini_settings_paths():
        if gp.exists():
            s = _load_json(gp)
            hooks = _gemini_hooks_from_settings(s)
            if hooks:
                global_gemini_hooks = hooks
                global_gemini_cfg_path = str(gp)
                break

    seen: set[tuple[str, str]] = set()

    for repo in repos:
        # ── Claude ────────────────────────────────────────────────────────────
        claude_cfg = repo / ".claude" / "settings.json"
        if claude_cfg.exists():
            s = _load_json(claude_cfg)
            rc = RepoConfig(
                repo_path=str(repo),
                agent="Claude",
                config_path=str(claude_cfg),
                hook_entries=_claude_hooks_from_settings(s),
                mcp_server_count=_claude_mcp_count(s),
            )
            configs.append(rc)
            seen.add((str(repo), "Claude"))
        else:
            # Check parent-dir inheritance
            parent_s, parent_path = _parent_config(repo, ".claude/settings.json")
            if parent_path:
                rc = RepoConfig(
                    repo_path=str(repo),
                    agent="Claude",
                    config_path=parent_path,
                    hook_entries=_claude_hooks_from_settings(parent_s),
                    mcp_server_count=_claude_mcp_count(parent_s),
                    inherited_from=parent_path,
                )
                configs.append(rc)
                seen.add((str(repo), "Claude"))
            elif global_claude_hooks:
                rc = RepoConfig(
                    repo_path=str(repo),
                    agent="Claude",
                    config_path=global_claude_cfg_path,
                    hook_entries=global_claude_hooks,
                    mcp_server_count=0,
                    inherited_from=global_claude_cfg_path,
                )
                configs.append(rc)
                seen.add((str(repo), "Claude"))

        # ── Gemini ────────────────────────────────────────────────────────────
        gemini_cfg = repo / ".gemini" / "settings.json"
        if gemini_cfg.exists():
            s = _load_json(gemini_cfg)
            rc = RepoConfig(
                repo_path=str(repo),
                agent="Gemini",
                config_path=str(gemini_cfg),
                hook_entries=_gemini_hooks_from_settings(s),
                mcp_server_count=_gemini_mcp_count(s),
            )
            configs.append(rc)
            seen.add((str(repo), "Gemini"))
        else:
            parent_s, parent_path = _parent_config(repo, ".gemini/settings.json")
            if parent_path:
                rc = RepoConfig(
                    repo_path=str(repo),
                    agent="Gemini",
                    config_path=parent_path,
                    hook_entries=_gemini_hooks_from_settings(parent_s),
                    mcp_server_count=_gemini_mcp_count(parent_s),
                    inherited_from=parent_path,
                )
                configs.append(rc)
                seen.add((str(repo), "Gemini"))
            elif global_gemini_hooks:
                rc = RepoConfig(
                    repo_path=str(repo),
                    agent="Gemini",
                    config_path=global_gemini_cfg_path,
                    hook_entries=global_gemini_hooks,
                    mcp_server_count=0,
                    inherited_from=global_gemini_cfg_path,
                )
                configs.append(rc)
                seen.add((str(repo), "Gemini"))

        # ── Zed ───────────────────────────────────────────────────────────────
        zed_cfg = repo / ".zed" / "settings.json"
        if zed_cfg.exists():
            configs.append(RepoConfig(
                repo_path=str(repo),
                agent="Zed",
                config_path=str(zed_cfg),
            ))
            seen.add((str(repo), "Zed"))

        # ── Antigravity / Shared Instructions ─────────────────────────────────
        ag_dir = repo / ".agents"
        if ag_dir.exists():
            configs.append(RepoConfig(
                repo_path=str(repo),
                agent="Antigravity",
                config_path=str(ag_dir),
            ))
            seen.add((str(repo), "Antigravity"))
        
        ag_file = repo / "AGENTS.md"
        if ag_file.exists() and (str(repo), "Antigravity") not in seen:
            configs.append(RepoConfig(
                repo_path=str(repo),
                agent="Antigravity/Shared",
                config_path=str(ag_file),
            ))
            seen.add((str(repo), "Antigravity/Shared"))

        # ── Artifact Detection (Antigravity) ──────────────────────────────────
        artifacts = []
        for art in ["implementation_plan.md", "walkthrough.md", "task.md"]:
            if (repo / art).exists():
                artifacts.append(art)
        
        # Attach artifacts to existing Antigravity configs or create a new one
        if artifacts:
            ag_configs = [c for c in configs if c.repo_path == str(repo) and "Antigravity" in c.agent]
            if ag_configs:
                for c in ag_configs:
                    c.artifact_files = artifacts
            else:
                # Create a "pseudo" Antigravity config if only artifacts exist
                configs.append(RepoConfig(
                    repo_path=str(repo),
                    agent="Antigravity (Artifacts)",
                    config_path=str(repo / artifacts[0]),
                    artifact_files=artifacts
                ))
                seen.add((str(repo), "Antigravity (Artifacts)"))

    # ── External Brain Discovery ──
    brain_configs = _probe_antigravity_brain()
    for bc in brain_configs:
        try:
            # Only include if it's within the scan_root (or scan_root is within it)
            if Path(bc.repo_path).is_relative_to(root) or root.is_relative_to(Path(bc.repo_path)):
                # Avoid duplicates
                if not any(c.repo_path == bc.repo_path and "Antigravity" in c.agent for c in configs):
                    configs.append(bc)
        except Exception:
            pass

    return configs
