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

`detect_agents()` probes 10 installation surfaces using a tiered strategy:

| Agent | Probe Method |
|---|---|
| Claude Code | `npm list -g @anthropic-ai/claude-code` + PATH lookup |
| Gemini CLI | `npm list -g @google/generative-ai` + PATH lookup |
| Aider | `pip show aider-chat` + PATH lookup |
| GitHub Copilot | VS Code extension directory scan |
| Continue.dev | VS Code extension + `~/.continue/` |
| Amazon Q | VS Code extension + `~/.aws/amazonq/` |
| Cody / Sourcegraph | VS Code extension directory scan |
| Cursor | `%APPDATA%\cursor\` (Windows) / `~/.cursor/` (Unix) |
| Windsurf / Codeium | `~/.windsurf/` / `~/.codeium/` |
| Claude Desktop | Presence of `claude_desktop_config.json` |

Each detected agent yields an `AgentInfo` record: name, version, install path, install method, and auth type.

### Config Crawler (`discovery/config_crawler.py`)

`crawl(scan_root)` walks the filesystem looking for agent config files:
- Claude Code: `.claude/settings.json`
- Gemini CLI: `.gemini/settings.json`

For each config file found, it parses:
- All registered hooks (event, matcher, command)
- MCP server count
- Whether any hook command matches known guard patterns (`coding-agent-guard`, `agentic_guard`)

**Hook Inheritance Resolution:** The crawler follows the same parent-directory walk that Claude Code and Gemini CLI use at runtime. A global config at `~/.claude/settings.json` is inherited by every repo that doesn't override it. The crawler materializes this inheritance chain so coverage analysis reflects what the agent actually loads, not just what's in the repo directory.

### MCP Inventory (`discovery/mcp_inventory.py`)

`inventory(scan_root)` collects MCP server registrations from five sources in priority order:

1. Claude Desktop (`claude_desktop_config.json`) — typically global, user-level trust
2. Claude Code global settings (`~/.claude/settings.json`)
3. Gemini CLI global settings (`~/.gemini/settings.json`)
4. Gemini extensions (`~/.gemini/extensions/*/gemini-extension.json`)
5. Per-repo configs (`.claude/settings.json`, `.gemini/settings.json` under scan root)

Each `McpServer` record captures: name, transport type (`local` / `remote`), command or URL, trust flag, originating agent, source file path, and declared tool count.

Remote-transport servers (HTTP URLs) with `trust: true` are flagged as `REMOTE_MCP_TRUST_TRUE` — the highest-severity finding category.

---

## Phase 2 — Analysis

### Gap Analyzer (`discovery/gap_analyzer.py`)

`analyze(repo_configs)` produces a `GapResult` for every (repo × agent) pair found during crawling. Three coverage states:

| Status | Meaning |
|---|---|
| `COVERED` | At least one hook in the resolved chain matches a known guard pattern |
| `SHADOW_HOOK` | Hooks exist but none are recognized guard commands — an unknown tool occupies the slot |
| `UNGUARDED` | No hooks registered for this agent in this repo or any parent config |

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
