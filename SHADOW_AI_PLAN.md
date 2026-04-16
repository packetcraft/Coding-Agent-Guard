# Shadow AI — Discovery Feature Plan

**Status:** Phases 1 & 2 complete and shipped — Phases 3 & 4 planned  
**Priority:** Active development  
**Audience:** IT / CISO teams — solving the "Shadow AI" problem on developer laptops

---

## Problem Statement

IT and CISO teams have no visibility into what AI coding agents are installed on developer machines,
what tools and external services those agents can reach, which repos are guarded vs unguarded,
or what excessive permissions exist. This is the **shadow AI** problem:
agents are quietly accumulating capabilities and network access that nobody is auditing.

Coding Agent Guard already solves the *runtime* enforcement problem (hooks intercepting tool calls).
This feature solves the *posture* problem: a continuous, queryable inventory of the entire AI attack
surface on a machine.

---

## Feature Name: Shadow AI

- Dashboard tab label: **Shadow AI**
- CLI command: `coding-agent-guard shadow-ai [--root <dir>] [--output json|text]`
- Audit event type: `DISCOVERY_SCAN`
- Existing audit log is reused — scan results land in the same JSONL files the dashboard already reads

---

## What Gets Discovered

### Tier 1 — Agent Inventory
Detect installed AI coding agents across all installation surfaces.

| Agent | Detection Method |
|---|---|
| Claude Code | `npm list -g`, PATH (`claude`) |
| Gemini CLI | `npm list -g` (`@google/gemini-cli`), PATH (`gemini`) |
| GitHub Copilot | VS Code extension `github.copilot*` |
| Cursor | App install, `~/.cursor/` |
| Windsurf / Codeium | App install, `~/.codeium/` |
| Continue.dev | VS Code extension `continue.continue`, `~/.continue/` |
| Amazon Q / CodeWhisperer | VS Code extension, `~/.aws/amazonq/` |
| Cody (Sourcegraph) | VS Code extension `sourcegraph.cody-ai` |
| Aider | pip package `aider-chat`, PATH |
| Claude Desktop | `$APPDATA/Claude/claude_desktop_config.json` |

Output per agent: name, version, install path, auth type (OAuth / API key / none detected).

### Tier 2 — Hook Surface
For each (repo × agent) pair:
- Does a hook config exist? (project-level or inherited from a parent-dir global)
- What hook events are registered? (`PreToolUse`, `PostToolUse`, `BeforeTool`, `AfterTool`)
- What matchers does each hook cover? Gaps matter — `Bash` hooked but `WebFetch` not is a blind spot.
- What command does each hook run? Is it our guard, another tool, or an unknown script?

### Tier 3 — MCP / Extension Surface
This is the largest blind spot for IT/CISO.

**Types of MCP servers:**
- **Local command**: `"command": "clasp"` — runs a local binary
- **Remote HTTP**: `"httpUrl": "https://..."` — outbound network call, tools entirely opaque without querying
- **Extension-bundled**: Gemini `~/.gemini/extensions/*/gemini-extension.json` can silently add MCP servers

**Key signals per MCP server:**
- Is it local or remote?
- Does it have `"trust": true` (skips user confirmation prompt)?
- What tools does it expose? (requires connecting and calling `tools/list` via MCP protocol)
- Is it covered by a guard hook, or completely unmonitored?

**Real finding from this machine (as of 2026-04-16):**
```
~/.gemini/extensions/gas-development-kit-extension/gemini-extension.json
  → mcpServers.workspace-developer:
      httpUrl: https://workspace-developer.goog/mcp
      trust: true          ← auto-connects, no user prompt
      tools: UNKNOWN       ← not enumerated, potential Google Workspace access
```

### Tier 4 — Trust & Permission Analysis

| Check | What to look for | Risk |
|---|---|---|
| Folder trust breadth | Gemini `trustedFolders.json` — parent-dir entries | Every cloned repo in that dir auto-trusts hooks |
| Orphaned trusted hooks | `trusted_hooks.json` — commands that no longer exist at that path | Stale approvals |
| Approval mode | Claude `--dangerously-skip-permissions`, Gemini yolo mode | Full bypass |
| API keys in env | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc. in env or `.env` files | Unmanaged credential |
| API keys in files | `.env`, `.env.local`, config files across repos | Credential sprawl |

**Real finding from this machine (as of 2026-04-16):**
```
~/.gemini/trustedFolders.json:
  "C:\\Users\\B006\\Documents\\github": "TRUST_FOLDER"
  ← Entire github/ parent dir trusted. Any new repo cloned there
    inherits hook execution rights without explicit approval.
```

### Tier 5 — Coverage Gap Analysis (core CISO view)

The primary output: which (repo × agent) pairs have NO guard?

```
Algorithm:
  for each repo in scanned tree:
    for each agent with config in that repo (or inherited from parent):
      is there a hook registered?
        yes → does the hook command resolve to a known guard?
          yes → COVERED
          no  → SHADOW HOOK  (something intercepting, but not our guard)
        no  → UNGUARDED
      does a folder-level or global hook cover it?
        yes → COVERED (inherited)
        no  → UNGUARDED
```

Output: a coverage map table — repo × agent × status × MCP count × risk flags.

---

## Data Sources (Filesystem Map)

```
Windows
├── %APPDATA%\Claude\claude_desktop_config.json      # Claude Desktop MCP
├── %USERPROFILE%\.claude\
│   ├── settings.json                                # Global hooks, permissions
│   ├── settings.local.json
│   └── plugins\*.json                              # Plugin marketplace entries
├── %USERPROFILE%\.gemini\
│   ├── settings.json                                # Global Gemini settings
│   ├── trustedFolders.json                          # Folder trust registry
│   ├── trusted_hooks.json                           # Historical hook approvals
│   └── extensions\*\gemini-extension.json           # Extension MCP bundles
├── %USERPROFILE%\.cursor\                           # Cursor config
├── %USERPROFILE%\.continue\                         # Continue.dev config
└── <scan-root>/ (e.g. ~/Documents/github/)
    └── per-repo:
        ├── .claude\settings.json
        └── .gemini\settings.json

VS Code / Cursor
└── settings.json → "github.copilot.*", "continue.*", "cody.*", "amazonQ.*"

macOS additions
├── ~/Library/Application Support/Claude/claude_desktop_config.json
└── ~/.config/ variants for Linux agents
```

---

## Proposed Module Architecture

```
coding_agent_guard/
  discovery/
    __init__.py
    scanner.py           # Orchestrator — runs probes, emits DISCOVERY_SCAN event
    agents.py            # Probe: installed agent binaries + versions + auth type
    config_crawler.py    # Probe: walk filesystem for all settings files
    mcp_inventory.py     # Probe: enumerate MCP servers, optionally call tools/list
    trust_analyzer.py    # Probe: folder trust breadth, orphaned hooks, API keys
    gap_analyzer.py      # Cross-ref: repos × agents → COVERED / SHADOW / UNGUARDED
    report.py            # Output: JSONL audit entry + human-readable summary
```

### New audit event type

```json
{
  "schema_version": "v1",
  "event_type": "DISCOVERY_SCAN",
  "timestamp": "...",
  "scan_id": "...",
  "scan_root": "C:/Users/B006/Documents/github",
  "summary": {
    "agents_found": 2,
    "repos_scanned": 14,
    "unguarded_pairs": 6,
    "shadow_hooks": 0,
    "remote_mcps": 1,
    "high_findings": 1,
    "medium_findings": 2
  },
  "findings": [
    {
      "id": "F-001",
      "category": "REMOTE_MCP_TRUST_TRUE",
      "severity": "HIGH",
      "agent": "Gemini",
      "source": "~/.gemini/extensions/gas-development-kit-extension/gemini-extension.json",
      "detail": "Remote MCP endpoint https://workspace-developer.goog/mcp with trust=true. Tools not enumerated.",
      "remediation": "Run posture scan with --enumerate-mcp to surface tools, or remove extension if unused."
    },
    {
      "id": "F-002",
      "category": "OVERLY_BROAD_FOLDER_TRUST",
      "severity": "MEDIUM",
      "agent": "Gemini",
      "source": "~/.gemini/trustedFolders.json",
      "detail": "Parent directory C:\\Users\\B006\\Documents\\github trusted as TRUST_FOLDER. All sub-repos inherit hook execution rights.",
      "remediation": "Replace parent-dir trust entry with individual repo entries."
    },
    {
      "id": "F-003",
      "category": "UNGUARDED_AGENT",
      "severity": "MEDIUM",
      "agent": "Claude",
      "repo": "C:/Users/B006/Documents/github/some-other-repo",
      "detail": "Claude Code active (global hook present) but no project-level guard hook and no MCP monitoring.",
      "remediation": "Run: python install_hooks.py /path/to/repo"
    }
  ]
}
```

---

## Dashboard Tab: Shadow AI

New tab added alongside Live Feed / Audit Explorer / Security Dashboard.

**Sections:**
1. **Coverage Map** — table: repo × agent × hook status (COVERED / SHADOW / UNGUARDED) × MCP count
2. **Agent Inventory** — installed agents, versions, auth types
3. **MCP Surface** — all configured MCP servers, local vs remote, trust flag, tool count (if enumerated)
4. **Findings** — sorted by severity, with remediation links
5. **Scan History** — delta between scans (new agents, new MCPs, new unguarded repos)

---

## CLI Interface

```bash
# Basic scan — filesystem walk from ~/Documents/github
coding-agent-guard shadow-ai

# Scan a specific root
coding-agent-guard shadow-ai --root /path/to/projects

# Include MCP tool enumeration (connects to each MCP server)
coding-agent-guard shadow-ai --enumerate-mcp

# Output as JSON (for SIEM ingestion)
coding-agent-guard shadow-ai --output json

# Compare to last scan (show deltas only)
coding-agent-guard shadow-ai --diff
```

---

## Why This Is Valuable to IT / CISO

1. **Continuous, not point-in-time** — runs on a schedule or as a pre-push hook; results land in the audit log the dashboard already reads.
2. **MCP tool enumeration** — actually calls `tools/list` on each MCP server to surface what the agent *can do*, not just what's configured. This is what a pentester would check.
3. **Gap scoring** — "14 repos, 3 agents, 6 unguarded pairs, 1 remote MCP with unknown tools" is a number that goes in a security report.
4. **Delta alerting** — new agent installed? New remote MCP added? New repo cloned into a trusted parent dir? Alert on change, not just current state.
5. **Exportable** — JSONL output feeds a SIEM, ServiceNow, or cloud posture dashboard (Wiz, Lacework, etc.).
6. **No agent modification required** — read-only filesystem scan; doesn't touch agent configs.

---

## Implementation Notes (for when this is built)

- MCP tool enumeration requires the `mcp` Python library or a minimal JSON-RPC client over stdio/HTTP.
- VS Code extension detection requires reading `%USERPROFILE%/.vscode/extensions/` directory — no VS Code API needed.
- The gap analyzer needs to understand folder-level hook inheritance (parent `.claude/settings.json` applies to all child repos).
- On Windows, paths in `trustedFolders.json` use Windows separators — normalize before comparison.
- `trusted_hooks.json` uses `"<name>:<command>"` format — the command half needs to be resolved against PATH to check liveness.
- The scanner should run in read-only mode by default and never write to agent config files.

---

## Decisions (Open Questions Resolved)

| Question | Decision |
|---|---|
| MCP enumeration opt-in? | Yes — `--enumerate-mcp` CLI flag only. UI also exposes a one-shot **Enumerate MCP** button. No automatic outbound calls. |
| Scan frequency? | Once per day maximum (auto). UI exposes a **Scan Now** button for on-demand runs. |
| Finding suppression? | Managed via the main web UI — users can mark a finding as suppressed (known-safe). No manual `patterns.yaml` edits required. Suppressions stored in a sidecar JSON file in the audit directory. |
| Multi-user / enterprise? | Out of scope. Single developer machine only — for personal use and learning. |

---

## Implementation Phases

The feature can be built in one continuous effort (~10 days) or shipped incrementally.
Phases 1+2 together form a releasable MVP that already answers the core CISO question.
Phase 4 (live MCP enumeration) is the highest-risk work and is cleanly separable.

### Phase 1 — Core Discovery ✅ COMPLETE (2026-04-16)
**Delivers:** "Which agents are installed and which repos are unguarded?"

- `agents.py` — detects 10 AI agents across npm global, pip, PATH, VS Code extensions, app dirs; auth type detection
- `config_crawler.py` — walks filesystem for all `.claude/settings.json` and `.gemini/settings.json`; resolves parent-dir hook inheritance up to 6 levels
- `gap_analyzer.py` — cross-references repos × agents → COVERED / SHADOW_HOOK / UNGUARDED
- `scanner.py` — orchestrator, emits `DISCOVERY_SCAN` JSONL to `audit/shadow_ai_scans.jsonl`
- `report.py` — human-readable text + JSON output
- `cli.py` — top-level dispatcher routing `shadow-ai` sub-command vs hook guard
- `setup.py` entry point updated: `coding_agent_guard.cli:main`
- CLI: `coding-agent-guard shadow-ai [--root <dir>] [--output json|text] [--no-audit]`
- 21 tests, all passing

**Validated on this machine:** 2 agents, 22 repo/agent pairs, 22/22 COVERED.

### Phase 2 — Trust & MCP Config Surface ✅ COMPLETE (2026-04-16)
**Delivers:** "What is the full attack surface, and what trust decisions have been made?"

- `trust_analyzer.py` — 6 checks: Gemini folder trust breadth, orphaned trusted hooks (real format: `{"repo": ["name:cmd",...]}` dict), API keys in env vars, API keys in `.env` files, remote MCPs with `trust=true`, unguarded repos
- `mcp_inventory.py` — enumerates MCP servers from Claude Desktop config, Claude global settings, Gemini global settings, Gemini extension manifests, and per-repo configs; classifies local vs remote; deduplicates by (name, source)
- Findings: `REMOTE_MCP_TRUST_TRUE` (HIGH), `OVERLY_BROAD_FOLDER_TRUST` (MEDIUM), `ORPHANED_HOOK` (LOW), `API_KEY_IN_ENV` (MEDIUM), `API_KEY_IN_FILE` (MEDIUM), `UNGUARDED_AGENT` (MEDIUM), `SHADOW_HOOK` (LOW)
- **Shadow AI** dashboard tab: metric row, Findings (collapsible, severity-ordered), Coverage Map, Agent Inventory, MCP Surface; **Scan Now** button in sidebar
- 40 tests (21 Phase 1 + 19 Phase 2), all passing

**Real findings on this machine:**
- **HIGH** — `workspace-developer.goog/mcp` via Gemini `gas-development-kit-extension`, `trust=true`, tools not enumerated
- **MEDIUM** — `~/.gemini/trustedFolders.json` trusts all of `Documents/github` (parent-dir trust)
- **LOW** — stale bare `coding-agent-guard` entry in `trusted_hooks.json` (bare command, not on PATH)

*Phases 1+2 = shippable MVP.*

### Phase 3 — UI Controls & Continuous Monitoring (~2 days)
**Delivers:** "Ongoing visibility without manual CLI runs."

- Daily auto-scan: on first dashboard load of the day, run scan if last scan was >24h ago
- **Scan History** section: delta between last two scans (new agents, new MCPs, newly unguarded repos highlighted in red)
- **Suppression UI**: mark a finding as suppressed (known-safe). Suppressions stored in `audit/shadow_ai_suppressions.json`. Suppressed findings shown greyed-out with a "Restore" option.
- Update CLI: `--diff` flag (compare to last scan, show deltas only)

*Note: Scan Now button already shipped in Phase 2. Daily auto-scan and delta/suppression are the remaining Phase 3 items.*

### Phase 4 — Live MCP Tool Enumeration (~3 days)
**Delivers:** "What can agents actually do via MCP, not just what's configured?"

- Extend `mcp_inventory.py` to optionally connect to each MCP server and call `tools/list` (MCP JSON-RPC protocol)
- Supports stdio transport (local command MCPs) and HTTP/SSE transport (remote MCPs)
- Requires `mcp` Python library (add to optional dependencies)
- Handles timeouts, auth failures, and unreachable servers gracefully — falls back to config-level data
- **Enumerate MCP** button in dashboard Shadow AI tab → runs enumeration for all configured servers, updates `tool_count` on each `McpServer`
- CLI: `--enumerate-mcp` flag
- New finding category: `MCP_TOOL_SURFACE` — lists tools exposed per server

*Phase 4 is fully independent once Phase 2 is done. Highest complexity due to MCP protocol + auth handling.*

---

## Effort Summary

| Phase | Scope | Status | Effort | Dependency |
|---|---|---|---|---|
| 1 — Core Discovery | Agent detect, config crawl, gap analysis, CLI | ✅ Done (2026-04-16) | ~3 days | None |
| 2 — Trust & MCP Config | Trust analyzer, MCP config inventory, dashboard tab | ✅ Done (2026-04-16) | ~2 days | Phase 1 |
| 3 — UI Controls | Daily auto-scan, delta view, suppression UI, `--diff` CLI | Planned | ~1.5 days | Phase 2 |
| 4 — MCP Enumeration | Live tools/list calls, Enumerate button | Planned | ~3 days | Phase 2 |
| **Total** | | | **~10 days** | |

*Scan Now button shipped early in Phase 2. Phase 3 remaining scope is ~1.5 days, not 2.*

**Phase 3 next steps (pick up here):**
1. Daily auto-scan — on first `_render_shadow_ai()` call of the day, check if `shadow_ai_scans.jsonl` last entry is >24h old; if so, run scan automatically before rendering
2. Scan History / delta section — load last two scan records, diff `coverage_map` and `mcp_servers`; surface new/removed entries highlighted
3. Suppression UI — `st.button("Suppress")` per finding; write to `audit/shadow_ai_suppressions.json`; filter suppressed findings from the main list, show greyed-out in a collapsed expander
4. `--diff` CLI flag — print only changed items vs the previous scan record in `shadow_ai_scans.jsonl`
