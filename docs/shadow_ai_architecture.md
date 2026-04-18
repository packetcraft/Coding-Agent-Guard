# Shadow AI Discovery — Strategy & Architecture

## Problem

Modern developer machines host multiple AI coding agents (Claude Code, Gemini CLI, Cursor, Aider, Copilot, etc.) installed independently across npm globals, pip packages, IDE extensions, and desktop apps. Each agent can load arbitrary MCP servers and register its own shell hooks. This creates an unaudited surface where:

- Agents operate without any security guard
- MCP servers with remote transports auto-connect without review
- Hook slots are filled by unknown tools (shadow hooks)
- Trust settings grant broader access than intended

Shadow AI Discovery scans the machine and produces a structured posture report covering all of this surface.

---

## Architecture Overview

```
coding-agent-guard shadow-ai [--root PATH]
         │
         ▼
  scanner.run_scan()          ← orchestrates all probes
         │
    ┌────┴───────────────────────────────┐
    │  Phase 1 — Inventory               │
    │  ├─ agents.detect_agents()         │  What agents are installed?
    │  ├─ config_crawler.crawl()         │  What configs & hooks exist?
    │  ├─ config_crawler._probe_brain()  │  Any active home-dir sessions?
    │  └─ mcp_inventory.inventory()      │  What MCP servers are registered?
    │                                    │
    │  Phase 2 — Analysis                │
    │  ├─ gap_analyzer.analyze()         │  Is each repo/agent pair guarded?
    │  └─ trust_analyzer.analyze()       │  Any high-risk posture findings?
    └────────────────────────────────────┘
         │
    ScanResult (dataclass)
         │
    ┌────┴──────────────────┐
    │  report.as_text()     │  Human-readable CLI output
    │  report.as_json()     │  Structured JSON for SIEM / audit log
    └───────────────────────┘
```

---

## Phase 1 — Inventory

### Agent Detection (`discovery/agents.py`)

`detect_agents()` probes 13 installation surfaces using a tiered strategy:

| Agent | Probe Method |
|---|---|
| VS Code | `shutil.which("code")` + Windows registry/path lookup |
| Zed | `shutil.which("zed")` + `%APPDATA%\Zed\` (Windows) / `~/.config/zed/` |
| Antigravity | `shutil.which("antigravity")` + `~/.gemini/antigravity/` |
| Claude Code | `npm list -g @anthropic-ai/claude-code` + PATH lookup |
| Gemini CLI | `npm list -g @google/gemini-cli` + PATH lookup |
| Aider | `pip show aider-chat` + PATH lookup |
| GitHub Copilot | VS Code extension directory scan |
| Continue.dev | VS Code extension + `~/.continue/` |
| Amazon Q | VS Code extension + `~/.aws/amazonq/` |
| Cody / Sourcegraph | VS Code extension directory scan |
| Cursor | `%APPDATA%\cursor\` (Windows) / `~/.cursor/` (Unix) |
| Windsurf / Codeium | `~/.windsurf/` / `~/.codeium/` |
| Claude Desktop | Presence of `claude_desktop_config.json` |

### Config Crawler (`discovery/config_crawler.py`)

`crawl(scan_root)` walks the filesystem looking for agent config files and instructions:
- Claude Code: `.claude/settings.json`
- Gemini CLI: `.gemini/settings.json`
- Zed: `.zed/settings.json`
- Antigravity: `.agents/` directory or `AGENTS.md` instruction files

For each config file found, it parses:
- All registered hooks (event, matcher, command)
- MCP server count
- Whether any hook command matches known guard patterns (`coding-agent-guard`, `agentic_guard`)

### External Brain Probe (`discovery/config_crawler.py`)

`_probe_antigravity_brain()` audits the local machine's "Digital Exhaust" to identify agents that don't use standard config files:
- Probes `~/.gemini/antigravity/brain/` for session artifacts.
- Extracts workspace file URIs (`file:///...`) from plans and walkthroughs.
- Maps discovered sessions back to absolute repository paths.
- Critical for identifying "Shadow AI" that has been cleaned from the project folder.

### MCP Inventory (`discovery/mcp_inventory.py`)

`inventory(scan_root)` collects MCP server registrations from seven sources in priority order:

1. Claude Desktop (`claude_desktop_config.json`)
2. Claude Code global settings (`~/.claude/settings.json`)
3. Gemini CLI global settings (`~/.gemini/settings.json`)
4. Gemini extensions (`~/.gemini/extensions/*/gemini-extension.json`)
5. Zed global settings (`%APPDATA%\Zed\settings.json` or `~/.config/zed/settings.json`)
6. Antigravity global settings (`~/.gemini/settings.json`)
7. Per-repo configs (`.claude/settings.json`, `.gemini/settings.json`, `.zed/settings.json`, `.agents/settings.json`)

Each `McpServer` record captures: name, transport type (`local` / `remote`), command or URL, trust flag, originating agent, source file path, and declared tool count.

Remote-transport servers (HTTP URLs) with `trust: true` are flagged as `REMOTE_MCP_TRUST_TRUE` — the highest-severity finding category.

---

## Phase 2 — Analysis

### Gap Analyzer (`discovery/gap_analyzer.py`)

`analyze(repo_configs)` produces a `GapResult` for every (repo × agent) pair found during crawling. Three coverage states:

| Status | Meaning |
|---|---|
| `COVERED` | At least one hook in the resolved chain matches a known guard pattern |
| `EXTERNAL_BRAIN` | Agent detected via home-dir session audit for this workspace |
| `ARTIFACT_ONLY` | Agent detected via in-repo artifacts (`task.md`, etc.) |
| `SHADOW_HOOK` | Hooks exist but none are recognized guard commands |
| `UNGUARDED` | No hooks or artifacts/brain sessions found for this agent |

**Why `SHADOW_HOOK` matters:** An attacker-controlled or misconfigured tool registered as a hook can intercept tool calls before (or instead of) a real guard. Shadow AI surfaces this so teams can audit what is actually running in hook position.

### Trust Analyzer (`discovery/trust_analyzer.py`)

`analyze(scan_root, mcp_servers, gap_results)` generates `Finding` objects with severity `HIGH`, `MEDIUM`, or `LOW`:

| Finding ID | Severity | Condition |
|---|---|---|
| `REMOTE_MCP_TRUST_TRUE` | HIGH | Remote MCP server with auto-trust enabled |
| `UNGUARDED_AGENT` | MEDIUM | Active agent with no guard hook anywhere in chain |
| `API_KEY_IN_ENV` | MEDIUM | API key pattern (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) in env vars |
| `API_KEY_IN_FILE` | MEDIUM | API key pattern found in `.env` files under scan root |
| `OVERLY_BROAD_FOLDER_TRUST` | MEDIUM | Gemini `trustedFolders` entry covers a very broad path (e.g., home dir) |
| `SHADOW_AI_EXTERNAL_BRAIN` | INFO | Active brain session detected via home-dir audit |
| `PASSIVE_MONITORING_ACTIVE` | INFO | Agent detected via in-repo artifacts |
| `SHADOW_HOOK` | LOW | Hook slot occupied by non-guard command |
| `ORPHANED_HOOK` | LOW | Hook command binary no longer exists on disk |

---

## Data Models (`discovery/__init__.py`)

```python
AgentInfo       name, version, install_path, install_method, auth_type
HookEntry       event, matcher, command, is_guard (bool)
RepoConfig      repo_path, agent, config_path, hook_entries[], mcp_count, inherited_from
GapResult       repo_path, agent, status, hook_command, inherited (bool), config_path
McpServer       name, transport, command, url, trust, agent, source, tool_count
Finding         id, category, severity, agent, source, detail, remediation
ScanResult      scan_id, timestamp, scan_root, agents_found[], repo_configs[],
                gap_results[], mcp_servers[], findings[]
```

---

## Output & Integration

### CLI

```bash
coding-agent-guard shadow-ai                        # scan from cwd
coding-agent-guard shadow-ai --root /path/to/scan   # explicit root
coding-agent-guard shadow-ai --output json           # JSON for SIEM
coding-agent-guard shadow-ai --no-audit              # skip writing scan to audit log
```

### Audit Log

Every scan appends one line to `audit/shadow_ai_scans.jsonl`:

```json
{
  "schema_version": "v1",
  "event_type": "DISCOVERY_SCAN",
  "scan_id": "...",
  "timestamp": "...",
  "agents_found": [...],
  "gap_results": [...],
  "mcp_servers": [...],
  "findings": [...]
}
```

### Dashboard

The **Shadow AI** tab in the Streamlit dashboard reads `shadow_ai_scans.jsonl`, shows the latest scan, and exposes a "Scan Now" button that triggers a live rescan. Metrics, findings table, coverage map, agent inventory, and MCP surface are all rendered from the same `ScanResult` structure.
