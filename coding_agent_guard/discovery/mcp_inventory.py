"""Probe: enumerate all configured MCP servers from agent config files."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from coding_agent_guard.discovery import McpServer


def _home() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE", Path.home()))
    return Path.home()


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


_EXEC_KEYWORDS = frozenset({
    "exec", "shell", "bash", "cmd", "run", "python", "node", "deno",
    "ruby", "process", "terminal", "subprocess", "spawn", "script",
})
_WRITE_KEYWORDS = frozenset({
    "write", "create", "delete", "upload", "modify", "edit", "save",
    "push", "deploy", "git", "file", "fs", "filesystem", "storage",
})
_NETWORK_KEYWORDS = frozenset({
    "fetch", "http", "curl", "web", "api", "request", "browser",
    "scrape", "download", "search", "slack", "email", "smtp",
})


def _classify_capability_tier(name: str, cmd: str | None, url: str | None) -> str:
    """Classify an MCP server into a capability risk tier."""
    tokens = set((name + " " + (cmd or "") + " " + (url or "")).lower().split())
    if tokens & _EXEC_KEYWORDS:
        return "exec"
    if tokens & _NETWORK_KEYWORDS or url:
        return "network"
    if tokens & _WRITE_KEYWORDS:
        return "write-local"
    return "read-only"


def _classify_mcp_entry(name: str, entry: dict, agent: str, source: str) -> McpServer:
    """Convert a raw MCP server dict into a McpServer dataclass."""
    # Determine transport
    http_url = entry.get("httpUrl") or entry.get("url")
    command = entry.get("command")

    if http_url:
        transport = "remote"
        cmd = None
        url = str(http_url)
    else:
        transport = "local"
        cmd_val = command or ""
        # command may be a string or the first element of an args list
        if isinstance(cmd_val, list):
            cmd_val = " ".join(cmd_val)
        args = entry.get("args", [])
        if args and isinstance(args, list):
            cmd = f"{cmd_val} {' '.join(str(a) for a in args)}".strip()
        else:
            cmd = str(cmd_val) if cmd_val else None
        url = None

    trust = bool(entry.get("trust", False))
    capability_tier = _classify_capability_tier(name, cmd, url)

    return McpServer(
        name=name,
        transport=transport,
        command=cmd,
        url=url,
        trust=trust,
        agent=agent,
        source=source,
        capability_tier=capability_tier,
    )


def _parse_mcp_servers(config: dict, agent: str, source: str) -> list[McpServer]:
    """Parse the mcpServers or context_servers section of any agent config dict."""
    servers: list[McpServer] = []
    # Claude/Gemini/Antigravity use mcpServers
    # Zed uses context_servers
    mcp_section = config.get("mcpServers") or config.get("context_servers")
    if not isinstance(mcp_section, dict):
        return servers
    for name, entry in mcp_section.items():
        if isinstance(entry, dict):
            servers.append(_classify_mcp_entry(name, entry, agent, source))
    return servers


# ── Per-source parsers ────────────────────────────────────────────────────────

def _zed_global_servers() -> list[McpServer]:
    if sys.platform == "win32":
        cfg_path = Path(os.environ.get("APPDATA", "")) / "Zed" / "settings.json"
    else:
        cfg_path = Path.home() / ".config" / "zed" / "settings.json"

    if not cfg_path.exists():
        return []
    return _parse_mcp_servers(_load_json(cfg_path), "Zed", str(cfg_path))


def _antigravity_global_servers() -> list[McpServer]:
    path = _home() / ".gemini" / "settings.json"
    if not path.exists():
        return []
    return _parse_mcp_servers(_load_json(path), "Antigravity", str(path))


def _claude_desktop_servers() -> list[McpServer]:
    if sys.platform == "win32":
        cfg_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "darwin":
        cfg_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        cfg_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

    if not cfg_path.exists():
        return []
    return _parse_mcp_servers(_load_json(cfg_path), "Claude Desktop", str(cfg_path))


def _claude_global_servers() -> list[McpServer]:
    servers: list[McpServer] = []
    for name in ("settings.json", "settings.local.json"):
        path = _home() / ".claude" / name
        if path.exists():
            servers.extend(_parse_mcp_servers(_load_json(path), "Claude Code", str(path)))
    return servers


def _gemini_global_servers() -> list[McpServer]:
    path = _home() / ".gemini" / "settings.json"
    if not path.exists():
        return []
    return _parse_mcp_servers(_load_json(path), "Gemini CLI", str(path))


def _gemini_extension_servers() -> list[McpServer]:
    """Parse MCP servers bundled inside Gemini extensions."""
    servers: list[McpServer] = []
    ext_root = _home() / ".gemini" / "extensions"
    if not ext_root.is_dir():
        return servers

    for ext_dir in sorted(ext_root.iterdir()):
        manifest = ext_dir / "gemini-extension.json"
        if not manifest.exists():
            continue
        data = _load_json(manifest)
        # Extensions embed mcpServers directly in the manifest
        mcp_section = data.get("mcpServers", {})
        if isinstance(mcp_section, dict):
            for name, entry in mcp_section.items():
                if isinstance(entry, dict):
                    servers.append(
                        _classify_mcp_entry(name, entry, "Gemini CLI (extension)", str(manifest))
                    )
    return servers


def _repo_level_servers(scan_root: str) -> list[McpServer]:
    """Walk scan_root for per-repo agent settings files and extract MCP entries."""
    servers: list[McpServer] = []
    root = Path(scan_root).expanduser().resolve()

    def _walk(p: Path, depth: int) -> None:
        if depth > 4:
            return
        
        # Mapping of relative config paths to Agent names
        # Antigravity/Gemini shared often
        configs = [
            (".claude/settings.json", "Claude Code"),
            (".gemini/settings.json", "Gemini CLI"),
            (".zed/settings.json",    "Zed"),
            (".agents/settings.json", "Antigravity"),
        ]
        
        for cfg_rel, agent in configs:
            cfg = p / cfg_rel
            if cfg.exists():
                servers.extend(_parse_mcp_servers(_load_json(cfg), agent, str(cfg)))
        
        # Don't descend into hidden dirs
        try:
            for child in sorted(p.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    _walk(child, depth + 1)
        except PermissionError:
            pass

    _walk(root, 0)
    return servers


# ── Public API ────────────────────────────────────────────────────────────────

def inventory(scan_root: str) -> list[McpServer]:
    """Return all MCP servers found across all config sources."""
    servers: list[McpServer] = []
    servers.extend(_claude_desktop_servers())
    servers.extend(_claude_global_servers())
    servers.extend(_gemini_global_servers())
    servers.extend(_gemini_extension_servers())
    servers.extend(_zed_global_servers())
    servers.extend(_antigravity_global_servers())
    servers.extend(_repo_level_servers(scan_root))

    # Deduplicate by (name, source) — extensions can re-export the same server
    seen: set[tuple[str, str]] = set()
    unique: list[McpServer] = []
    for s in servers:
        key = (s.name, s.source)
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique
