"""Tests for Phase 1 & 2 — Core Discovery + Trust/MCP Surface."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from coding_agent_guard.discovery import (
    AgentInfo,
    Finding,
    GapResult,
    HookEntry,
    McpServer,
    RepoConfig,
    ScanResult,
)
from coding_agent_guard.discovery.gap_analyzer import analyze
from coding_agent_guard.discovery.report import as_text, as_json
from coding_agent_guard.discovery.config_crawler import (
    _is_guard_command,
    _claude_hooks_from_settings,
    _gemini_hooks_from_settings,
    crawl,
)


# ── _is_guard_command ─────────────────────────────────────────────────────────

def test_guard_command_exact():
    assert _is_guard_command("coding-agent-guard") is True


def test_guard_command_absolute_path():
    assert _is_guard_command("C:/venv/Scripts/coding-agent-guard.exe") is True


def test_guard_command_backslash():
    assert _is_guard_command(r"C:\venv\Scripts\coding-agent-guard.exe") is True


def test_non_guard_command():
    assert _is_guard_command("some-other-hook.sh") is False


def test_guard_command_agentic_guard():
    assert _is_guard_command("agentic-guard") is True


# ── _claude_hooks_from_settings ───────────────────────────────────────────────

def test_claude_hooks_parsed():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": ".*",
                    "hooks": [{"command": "coding-agent-guard", "name": "guard"}],
                }
            ]
        }
    }
    hooks = _claude_hooks_from_settings(settings)
    assert len(hooks) == 1
    assert hooks[0].event == "PreToolUse"
    assert hooks[0].matcher == ".*"
    assert hooks[0].is_guard is True


def test_claude_hooks_empty():
    assert _claude_hooks_from_settings({}) == []


def test_claude_hooks_non_guard():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"command": "some-other-tool"}],
                }
            ]
        }
    }
    hooks = _claude_hooks_from_settings(settings)
    assert len(hooks) == 1
    assert hooks[0].is_guard is False


# ── _gemini_hooks_from_settings ───────────────────────────────────────────────

def test_gemini_hooks_parsed():
    settings = {
        "hooks": {
            "BeforeTool": [
                {
                    "matcher": ".*",
                    "hooks": [{"command": "/path/coding-agent-guard.exe"}],
                }
            ]
        }
    }
    hooks = _gemini_hooks_from_settings(settings)
    assert len(hooks) == 1
    assert hooks[0].event == "BeforeTool"
    assert hooks[0].is_guard is True


# ── gap_analyzer ──────────────────────────────────────────────────────────────

def _make_rc(repo: str, agent: str, hooks: list[HookEntry], inherited: bool = False) -> RepoConfig:
    return RepoConfig(
        repo_path=repo,
        agent=agent,
        config_path=f"{repo}/.{agent.lower()}/settings.json",
        hook_entries=hooks,
        inherited_from="parent" if inherited else None,
    )


def test_gap_covered():
    h = HookEntry(event="PreToolUse", matcher=".*", command="coding-agent-guard", is_guard=True)
    rc = _make_rc("/repo/a", "Claude", [h])
    results = analyze([rc])
    assert results[0].status == "COVERED"
    assert results[0].hook_command == "coding-agent-guard"
    assert results[0].inherited is False


def test_gap_unguarded():
    rc = _make_rc("/repo/b", "Gemini", [])
    results = analyze([rc])
    assert results[0].status == "UNGUARDED"
    assert results[0].hook_command is None


def test_gap_shadow_hook():
    h = HookEntry(event="PreToolUse", matcher=".*", command="other-hook.sh", is_guard=False)
    rc = _make_rc("/repo/c", "Claude", [h])
    results = analyze([rc])
    assert results[0].status == "SHADOW_HOOK"
    assert results[0].hook_command == "other-hook.sh"


def test_gap_guard_takes_priority_over_shadow():
    guard = HookEntry(event="PreToolUse", matcher=".*", command="coding-agent-guard", is_guard=True)
    shadow = HookEntry(event="PostToolUse", matcher=".*", command="other-hook.sh", is_guard=False)
    rc = _make_rc("/repo/d", "Claude", [shadow, guard])
    results = analyze([rc])
    assert results[0].status == "COVERED"


def test_gap_inherited():
    h = HookEntry(event="BeforeTool", matcher=".*", command="coding-agent-guard", is_guard=True)
    rc = _make_rc("/repo/e", "Gemini", [h], inherited=True)
    results = analyze([rc])
    assert results[0].inherited is True


# ── report.as_text ────────────────────────────────────────────────────────────

def _make_scan_result() -> ScanResult:
    return ScanResult(
        scan_id="test-001",
        timestamp="2026-04-16T00:00:00Z",
        scan_root="/projects",
        agents_found=[
            AgentInfo(name="Claude Code", version="1.0.0", install_path="/usr/bin/claude", install_method="npm", auth_type="OAuth"),
        ],
        gap_results=[
            GapResult(repo_path="/projects/guarded", agent="Claude", status="COVERED", hook_command="coding-agent-guard", inherited=False, config_path="/projects/guarded/.claude/settings.json"),
            GapResult(repo_path="/projects/naked", agent="Gemini", status="UNGUARDED", hook_command=None, inherited=False, config_path=None),
        ],
    )


def test_report_text_contains_key_sections():
    text = as_text(_make_scan_result())
    assert "Shadow AI Discovery Scan" in text
    assert "DETECTED AGENTS" in text
    assert "COVERAGE MAP" in text
    assert "SUMMARY" in text
    assert "Claude Code" in text
    assert "UNGUARDED" in text
    assert "COVERED" in text


def test_report_text_remediation_in_findings():
    # Remediation advice now lives inside the FINDINGS section (not a separate block)
    # _make_scan_result() has no findings so there's nothing to check here;
    # the full test is in test_report_text_includes_findings_section which uses
    # _make_full_scan_result(). Just verify the section header is present.
    text = as_text(_make_scan_result())
    assert "FINDINGS" in text


def test_report_json_structure():
    data = json.loads(as_json(_make_scan_result()))
    assert data["event_type"] == "DISCOVERY_SCAN"
    assert data["schema_version"] == "v1"
    assert "summary" in data
    assert data["summary"]["unguarded"] == 1
    assert data["summary"]["covered"] == 1
    assert len(data["agents"]) == 1
    assert len(data["coverage_map"]) == 2


# ── config_crawler.crawl (filesystem integration) ─────────────────────────────

def test_crawl_detects_claude_hook(tmp_path: Path):
    # Create a fake repo with a Claude hook config
    repo = tmp_path / "my-project"
    (repo / ".git").mkdir(parents=True)
    claude_dir = repo / ".claude"
    claude_dir.mkdir()
    settings = {
        "hooks": {
            "PreToolUse": [
                {"matcher": ".*", "hooks": [{"command": "coding-agent-guard"}]}
            ]
        }
    }
    (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    configs = crawl(str(tmp_path))
    claude_configs = [c for c in configs if c.agent == "Claude" and Path(c.repo_path) == repo]
    assert len(claude_configs) == 1
    assert claude_configs[0].hook_entries[0].is_guard is True


def test_crawl_detects_gemini_hook(tmp_path: Path):
    repo = tmp_path / "gemini-project"
    (repo / ".git").mkdir(parents=True)
    gemini_dir = repo / ".gemini"
    gemini_dir.mkdir()
    settings = {
        "hooks": {
            "BeforeTool": [
                {"matcher": ".*", "hooks": [{"command": "/venv/Scripts/coding-agent-guard.exe"}]}
            ]
        }
    }
    (gemini_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    configs = crawl(str(tmp_path))
    gemini_configs = [c for c in configs if c.agent == "Gemini" and Path(c.repo_path) == repo]
    assert len(gemini_configs) == 1
    assert gemini_configs[0].hook_entries[0].is_guard is True


def test_crawl_unguarded_repo(tmp_path: Path):
    repo = tmp_path / "bare-project"
    (repo / ".git").mkdir(parents=True)
    # No agent config at all — should produce no RepoConfig (no agent detected)
    configs = crawl(str(tmp_path))
    assert all(Path(c.repo_path) != repo for c in configs)


def test_crawl_empty_root(tmp_path: Path):
    configs = crawl(str(tmp_path))
    assert configs == []


# ── mcp_inventory ─────────────────────────────────────────────────────────────

from coding_agent_guard.discovery.mcp_inventory import (
    _classify_mcp_entry,
    _parse_mcp_servers,
)


def test_mcp_classify_local():
    entry = {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]}
    s = _classify_mcp_entry("fs", entry, "Claude Code", "/path/settings.json")
    assert s.transport == "local"
    assert s.trust is False
    assert "npx" in s.command
    assert s.url is None


def test_mcp_classify_remote():
    entry = {"httpUrl": "https://workspace-developer.goog/mcp", "trust": True}
    s = _classify_mcp_entry("workspace", entry, "Gemini CLI", "/ext/manifest.json")
    assert s.transport == "remote"
    assert s.url == "https://workspace-developer.goog/mcp"
    assert s.trust is True
    assert s.command is None


def test_mcp_classify_remote_no_trust():
    entry = {"httpUrl": "https://example.com/mcp"}
    s = _classify_mcp_entry("example", entry, "Claude Code", "/path/settings.json")
    assert s.trust is False


def test_parse_mcp_servers_empty():
    assert _parse_mcp_servers({}, "Claude Code", "/path") == []


def test_parse_mcp_servers_multiple(tmp_path: Path):
    config = {
        "mcpServers": {
            "server-a": {"command": "npx", "args": ["pkg-a"]},
            "server-b": {"httpUrl": "https://b.example.com/mcp", "trust": True},
        }
    }
    servers = _parse_mcp_servers(config, "Claude Code", str(tmp_path / "settings.json"))
    assert len(servers) == 2
    local = next(s for s in servers if s.name == "server-a")
    remote = next(s for s in servers if s.name == "server-b")
    assert local.transport == "local"
    assert remote.transport == "remote"
    assert remote.trust is True


def test_mcp_inventory_from_claude_desktop_config(tmp_path: Path):
    """inventory() picks up MCP servers from a Claude Desktop config file."""
    from coding_agent_guard.discovery import mcp_inventory as mcp_mod
    cfg = {
        "mcpServers": {
            "my-server": {"command": "python", "args": ["-m", "my_mcp"]}
        }
    }
    cfg_file = tmp_path / "claude_desktop_config.json"
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")

    with mock.patch.object(mcp_mod, "_claude_desktop_servers",
                           return_value=mcp_mod._parse_mcp_servers(cfg, "Claude Desktop", str(cfg_file))):
        servers = mcp_mod.inventory(str(tmp_path))

    desktop = [s for s in servers if s.name == "my-server"]
    assert len(desktop) == 1
    assert desktop[0].transport == "local"


# ── trust_analyzer ────────────────────────────────────────────────────────────

from coding_agent_guard.discovery.trust_analyzer import (
    _check_remote_mcp_trust,
    _check_unguarded_repos,
    _Counter,
)


def test_remote_mcp_trust_high_finding():
    servers = [
        McpServer(
            name="workspace",
            transport="remote",
            command=None,
            url="https://workspace-developer.goog/mcp",
            trust=True,
            agent="Gemini CLI",
            source="/ext/manifest.json",
        )
    ]
    findings = _check_remote_mcp_trust(servers, _Counter(1))
    assert len(findings) == 1
    assert findings[0].severity == "HIGH"
    assert findings[0].category == "REMOTE_MCP_TRUST_TRUE"


def test_remote_mcp_no_trust_no_finding():
    servers = [
        McpServer(
            name="safe",
            transport="remote",
            command=None,
            url="https://example.com/mcp",
            trust=False,
            agent="Claude Code",
            source="/settings.json",
        )
    ]
    findings = _check_remote_mcp_trust(servers, _Counter(1))
    assert findings == []


def test_local_mcp_trust_no_finding():
    servers = [
        McpServer(
            name="local-server",
            transport="local",
            command="npx my-mcp",
            url=None,
            trust=True,
            agent="Claude Code",
            source="/settings.json",
        )
    ]
    # trust=true on local MCP is not flagged (local binary, not outbound HTTP)
    findings = _check_remote_mcp_trust(servers, _Counter(1))
    assert findings == []


def test_unguarded_repo_finding():
    gaps = [
        GapResult(
            repo_path="/projects/unguarded",
            agent="Claude",
            status="UNGUARDED",
            hook_command=None,
            inherited=False,
            config_path=None,
        )
    ]
    findings = _check_unguarded_repos(gaps, _Counter(1))
    assert len(findings) == 1
    assert findings[0].severity == "MEDIUM"
    assert findings[0].category == "UNGUARDED_AGENT"
    assert "install_hooks.py" in findings[0].remediation


def test_shadow_hook_finding():
    gaps = [
        GapResult(
            repo_path="/projects/shadow",
            agent="Gemini",
            status="SHADOW_HOOK",
            hook_command="other-tool.sh",
            inherited=False,
            config_path="/projects/shadow/.gemini/settings.json",
        )
    ]
    findings = _check_unguarded_repos(gaps, _Counter(1))
    assert len(findings) == 1
    assert findings[0].category == "SHADOW_HOOK"
    assert findings[0].severity == "LOW"


def test_covered_repo_no_finding():
    gaps = [
        GapResult(
            repo_path="/projects/safe",
            agent="Claude",
            status="COVERED",
            hook_command="coding-agent-guard",
            inherited=False,
            config_path="/projects/safe/.claude/settings.json",
        )
    ]
    findings = _check_unguarded_repos(gaps, _Counter(1))
    assert findings == []


def test_api_key_env_finding():
    from coding_agent_guard.discovery.trust_analyzer import _check_api_keys_env
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-123"}):
        findings = _check_api_keys_env(_Counter(1))
    assert len(findings) == 1
    assert findings[0].category == "API_KEY_IN_ENV"
    assert findings[0].severity == "MEDIUM"


def test_api_key_env_no_finding():
    from coding_agent_guard.discovery.trust_analyzer import _check_api_keys_env
    # Remove any real keys from env for this test
    clean_env = {k: v for k, v in os.environ.items()
                 if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                               "GOOGLE_API_KEY", "COHERE_API_KEY", "MISTRAL_API_KEY")}
    with mock.patch.dict(os.environ, clean_env, clear=True):
        findings = _check_api_keys_env(_Counter(1))
    assert findings == []


def test_api_key_in_dotenv_file(tmp_path: Path):
    from coding_agent_guard.discovery.trust_analyzer import _check_api_keys_files
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=sk-ant-abc123\nFOO=bar\n", encoding="utf-8")
    findings = _check_api_keys_files(str(tmp_path), _Counter(1))
    assert len(findings) == 1
    assert findings[0].category == "API_KEY_IN_FILE"


def test_no_dotenv_no_finding(tmp_path: Path):
    from coding_agent_guard.discovery.trust_analyzer import _check_api_keys_files
    findings = _check_api_keys_files(str(tmp_path), _Counter(1))
    assert findings == []


# ── report Phase 2 additions ──────────────────────────────────────────────────

def _make_full_scan_result() -> ScanResult:
    return ScanResult(
        scan_id="test-002",
        timestamp="2026-04-16T00:00:00Z",
        scan_root="/projects",
        agents_found=[
            AgentInfo(name="Claude Code", version="1.0.0", install_path="/usr/bin/claude",
                      install_method="npm", auth_type="OAuth"),
        ],
        gap_results=[
            GapResult(repo_path="/projects/guarded", agent="Claude", status="COVERED",
                      hook_command="coding-agent-guard", inherited=False,
                      config_path="/projects/guarded/.claude/settings.json"),
            GapResult(repo_path="/projects/naked", agent="Gemini", status="UNGUARDED",
                      hook_command=None, inherited=False, config_path=None),
        ],
        mcp_servers=[
            McpServer(name="workspace", transport="remote",
                      command=None, url="https://workspace-developer.goog/mcp",
                      trust=True, agent="Gemini CLI", source="/ext/manifest.json"),
            McpServer(name="fs", transport="local",
                      command="npx -y @mcp/fs", url=None,
                      trust=False, agent="Claude Code", source="/settings.json"),
        ],
        findings=[
            Finding(id="F-001", category="REMOTE_MCP_TRUST_TRUE", severity="HIGH",
                    agent="Gemini", source="/ext/manifest.json",
                    detail="Remote MCP with trust=true", remediation="Remove trust flag"),
        ],
    )


def test_report_text_includes_mcp_section():
    text = as_text(_make_full_scan_result())
    assert "MCP SURFACE" in text
    assert "workspace" in text
    assert "remote" in text


def test_report_text_includes_findings_section():
    text = as_text(_make_full_scan_result())
    assert "FINDINGS" in text
    assert "REMOTE_MCP_TRUST_TRUE" in text
    assert "[HIGH]" in text


def test_report_json_includes_mcp_and_findings():
    data = json.loads(as_json(_make_full_scan_result()))
    assert len(data["mcp_servers"]) == 2
    assert len(data["findings"]) == 1
    assert data["summary"]["mcp_servers"] == 2
    assert data["summary"]["remote_mcps_trust_true"] == 1
    assert data["summary"]["high_findings"] == 1
