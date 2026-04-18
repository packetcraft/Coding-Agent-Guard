# Shadow AI Discovery — Strategy & Architecture

## Problem

Modern developer machines host multiple AI coding agents (Claude Code, Gemini CLI, Cursor, Aider, Copilot, Ollama, etc.) installed independently across npm globals, pip packages, IDE extensions, desktop apps, and CI/CD pipelines. Each agent can load arbitrary MCP servers and register its own shell hooks. This creates an unaudited surface where:

- Agents operate without any security guard
- Guard hooks are registered but their binaries are silently missing — the repo appears COVERED but calls pass through uninspected
- MCP servers with remote transports auto-connect without review, exposing exec- or network-tier capabilities
- Hook slots are filled by unknown tools (shadow hooks)
- Trust settings grant broader access than intended
- Agent memory files accumulate credentials that can be exfiltrated via prompt injection
- CI/CD pipelines embed AI agents with no hook interception layer at all

Shadow AI Discovery scans the machine and produces a structured posture report covering all of this surface.

---

## Architecture Overview

```
coding-agent-guard shadow-ai [--root PATH] [--diff] [--fix]
         │
         ▼
  scanner.run_scan()              ← orchestrates all probes
         │
    ┌────┴───────────────────────────────────────┐
    │  Phase 1 — Inventory                        │
    │  ├─ agents.detect_agents()                  │  What agents are installed?
    │  ├─ agents.detect_cicd_agents()             │  Any AI agents in CI/CD pipelines?
    │  ├─ config_crawler.crawl()                  │  What configs & hooks exist?
    │  ├─ config_crawler._probe_brain()           │  Any active home-dir sessions?
    │  └─ mcp_inventory.inventory()               │  What MCP servers are registered?
    │                                             │
    │  Phase 2 — Analysis                         │
    │  ├─ gap_analyzer.analyze()                  │  Is each repo/agent pair guarded?
    │  │    └─ _check_hook_liveness()             │  Is the guard binary actually alive?
    │  └─ trust_analyzer.analyze()                │  Any high-risk posture findings?
    │       ├─ _check_memory_files_secrets()      │  Secrets in agent memory files?
    │       ├─ _check_dangerous_mcp_capabilities()│  Exec/network-tier MCP servers?
    │       └─ _check_cicd_agents()               │  Unguarded pipeline agents?
    └─────────────────────────────────────────────┘
         │
    ScanResult (dataclass)
         │
    ┌────┴──────────────────────┐
    │  report.as_text()          │  Human-readable CLI output
    │  report.as_json()          │  Structured JSON for SIEM / audit log
    │  scanner.diff_scans()      │  Posture drift between two scans
    │  scanner._apply_fix()      │  Interactive hook remediation
    └────────────────────────────┘
```

---

## Phase 1 — Inventory

### Agent Detection (`discovery/agents.py`)

`detect_agents()` probes 17 installation surfaces using a tiered strategy:

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
| Windsurf / Codeium | `~/.codeium/` |
| Claude Desktop | Presence of `claude_desktop_config.json` |
| **Ollama** | `shutil.which("ollama")` + `~/.ollama/` |
| **LM Studio** | `%APPDATA%\LM-Studio\` (Windows) / `~/Library/Application Support/LM-Studio/` (macOS) |
| **Open Interpreter** | `pip show open-interpreter` + `shutil.which("interpreter")` |
| **GitHub Copilot CLI** | `shutil.which("gh")` + `gh extension list` (checks for copilot extension) |

`detect_cicd_agents(scan_root)` walks `.github/workflows/*.yml` under the scan root and matches against known AI action references:

| Pattern | Agent Name |
|---|---|
| `anthropic-ai/claude-github-action` | Claude (GitHub Action) |
| `anthropics/claude-code-action` | Claude Code (GitHub Action) |
| `github/copilot-workspace-action` | Copilot Workspace (GitHub Action) |
| `devin-ai-integration/devin-action` | Devin (GitHub Action) |
| `google-github-actions/gemini` | Gemini (GitHub Action) |
| `openai/openai-action` | OpenAI (GitHub Action) |
| `continuedev/continue-action` | Continue.dev (GitHub Action) |

CI/CD agents are reported with `install_method: "ci_pipeline"` and always generate a `CICD_AGENT_UNGUARDED` finding — pipeline agents have no hook interception layer.

### Config Crawler (`discovery/config_crawler.py`)

`crawl(scan_root)` walks the filesystem for agent config files, resolving a 6-level parent-directory inheritance chain:

- Claude Code: `.claude/settings.json`
- Gemini CLI: `.gemini/settings.json`
- Zed: `.zed/settings.json`
- Antigravity: `.agents/` directory or `AGENTS.md`

For each config, it parses hooks (event, matcher, command), MCP server count, and whether any hook matches known guard patterns (`coding-agent-guard`, `agentic_guard`, `agentic-guard`). Inheritance is resolved from repo-level → parent dirs → global config (`~/.claude/`, `~/.gemini/`).

### External Brain Probe (`discovery/config_crawler.py`)

`_probe_antigravity_brain()` audits "Digital Exhaust" to identify agents that have been cleaned from the project folder:

- Probes `~/.gemini/antigravity/brain/` (and `~/Library/Application Support/Antigravity/brain/` on macOS) for session artifacts
- Extracts workspace file URIs (`file:///...`) from `implementation_plan.md` and `walkthrough.md`
- Walks up from each discovered path to find the repo root (`.git`, `.claude`, `.gemini`)
- Maps active sessions back to absolute repository paths

### MCP Inventory (`discovery/mcp_inventory.py`)

`inventory(scan_root)` collects MCP server registrations from seven sources:

1. Claude Desktop (`claude_desktop_config.json`)
2. Claude Code global settings (`~/.claude/settings.json`, `~/.claude/settings.local.json`)
3. Gemini CLI global settings (`~/.gemini/settings.json`)
4. Gemini extensions (`~/.gemini/extensions/*/gemini-extension.json`)
5. Zed global settings
6. Antigravity global settings
7. Per-repo configs (`.claude/settings.json`, `.gemini/settings.json`, `.zed/settings.json`, `.agents/settings.json`)

Each `McpServer` record now captures a **capability tier** via `_classify_capability_tier()`:

| Tier | Classification Logic |
|---|---|
| `exec` | Name or command contains exec/shell/bash/python/node/terminal/subprocess keywords |
| `network` | Remote transport (HTTP URL), or name/command contains fetch/http/curl/web/api/browser keywords |
| `write-local` | Name or command contains write/create/delete/upload/modify/git/deploy keywords |
| `read-only` | None of the above match |

---

## Phase 2 — Analysis

### Gap Analyzer (`discovery/gap_analyzer.py`)

`analyze(repo_configs)` produces a `GapResult` for every (repo × agent) pair. Coverage statuses, now including liveness validation:

| Status | Meaning |
|---|---|
| `COVERED` | Guard hook registered **and** binary verified alive via `_check_hook_liveness()` |
| `BROKEN_HOOK` | Guard hook registered but binary cannot be resolved — appears covered, actually unprotected |
| `SHADOW_HOOK` | Hooks exist but none are recognized guard commands |
| `ARTIFACT_ONLY` | Agent detected via in-repo artifacts (`task.md`, etc.) — passive monitoring only |
| `EXTERNAL_BRAIN` | Agent detected via home-dir brain session audit |
| `UNGUARDED` | No hooks, artifacts, or brain sessions found |

**`BROKEN_HOOK` is the most dangerous status** — it gives a false sense of security. The scan surfaces it as a HIGH severity finding to avoid silent unprotected gaps.

`_check_hook_liveness(command)` extracts the first token of the hook command and checks:
1. Absolute/relative path: `Path(binary).exists()`
2. PATH lookup: `shutil.which(binary) is not None`

### Trust Analyzer (`discovery/trust_analyzer.py`)

`analyze(scan_root, agents_found, mcp_servers, gap_results)` generates `Finding` objects across 9 categories:

| Category | Severity | Condition |
|---|---|---|
| `BROKEN_HOOK` | HIGH | Guard hook registered but binary missing |
| `SECRET_IN_AGENT_MEMORY` | HIGH | Credential pattern in `~/.claude/`, `~/.gemini/`, or brain session files |
| `REMOTE_MCP_TRUST_TRUE` | HIGH | Remote MCP server with `trust: true` |
| `DANGEROUS_MCP_CAPABILITY_EXEC` | HIGH | MCP server classified as `exec` tier |
| `DANGEROUS_MCP_CAPABILITY_NETWORK` | MEDIUM | MCP server classified as `network` tier |
| `CICD_AGENT_UNGUARDED` | MEDIUM | AI agent found in a CI/CD workflow file |
| `UNGUARDED_AGENT` | MEDIUM | Active agent with no guard hook anywhere in the resolution chain |
| `API_KEY_IN_ENV` / `API_KEY_IN_FILE` | MEDIUM | API key in environment vars or `.env` files |
| `OVERLY_BROAD_FOLDER_TRUST` | MEDIUM | Gemini `trustedFolders` entry covers a parent directory |
| `SHADOW_HOOK` | LOW | Hook slot occupied by a non-guard command |
| `ORPHANED_HOOK` | LOW | Hook command binary no longer exists |
| `PASSIVE_MONITORING_ACTIVE` | INFO | Agent detected via artifacts only |
| `SHADOW_AI_EXTERNAL_BRAIN` | INFO | Active brain session detected via home-dir audit |

**Memory secrets scan** (`_check_memory_files_secrets`) scans:
- `~/.claude/CLAUDE.md`, `~/.claude/memory.md`
- `~/.gemini/GEMINI.md`, `~/.gemini/memory.md`
- All brain session artifact files

Using patterns: `sk-[A-Za-z0-9]{20,}`, `AIza[A-Za-z0-9]{35}`, `ghp_/gho_` GitHub tokens, and env-style key assignments.

---

## Posture Drift (`scanner.diff_scans`)

`diff_scans(current, previous)` compares two scan dicts and returns:

```python
{
  "from_scan_id": "...",
  "to_scan_id": "...",
  "posture_score_delta": +5.0,          # score change
  "new_agents": ["Ollama"],             # appeared since last scan
  "removed_agents": [],
  "newly_unprotected": [               # were COVERED, now aren't
    {"repo_path": "...", "agent": "Claude", "old_status": "COVERED", "new_status": "BROKEN_HOOK"}
  ],
  "newly_protected": [],               # were UNGUARDED, now COVERED
  "new_mcp_servers": [],
  "removed_mcp_servers": [],
}
```

Accessible via `--diff` CLI flag or the drift panel in the **AI Posture & Discovery** dashboard tab.

---

## Remediation Auto-fix (`scanner._apply_fix`)

`--fix` mode generates a `hooks` block for each unguarded or broken-hook Claude repo:

```json
{
  "hooks": {
    "PreToolUse":  [{"matcher": ".*", "hooks": [{"type": "command", "command": "<guard_bin> pre-tool-use"}]}],
    "PostToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": "<guard_bin> post-tool-use"}]}]
  }
}
```

Before writing, it shows the exact JSON that will be merged into `.claude/settings.json` and requires explicit `y` confirmation per repo. Existing settings are preserved — the hook block is merged, not overwritten.

---

## Data Models (`discovery/__init__.py`)

```python
AgentInfo    name, version, install_path, install_method, auth_type

HookEntry    event, matcher, command, is_guard (bool)

RepoConfig   repo_path, agent, config_path, hook_entries[], mcp_count,
             inherited_from, artifact_files[], external_brain_session

GapResult    repo_path, agent, status, hook_command, inherited (bool),
             config_path, artifact_files[], external_brain_session,
             hook_healthy (bool | None)        ← NEW: False = binary missing

McpServer    name, transport, command, url, trust, agent, source,
             tool_count, capability_tier       ← NEW: "exec"|"network"|"write-local"|"read-only"

Finding      id, category, severity, agent, source, detail, remediation

ScanResult   scan_id, timestamp, scan_root, agents_found[], repo_configs[],
             gap_results[], mcp_servers[], findings[]
```

---

## Output & Integration

### CLI

```bash
coding-agent-guard shadow-ai                          # scan, text output
coding-agent-guard shadow-ai --root /path/to/scan     # explicit scan root
coding-agent-guard shadow-ai --output json            # JSON for SIEM/export
coding-agent-guard shadow-ai --no-audit               # skip audit log write
coding-agent-guard shadow-ai --diff                   # show posture drift vs last scan
coding-agent-guard shadow-ai --fix                    # interactive remediation
```

### Audit Log

Every scan appends one line to `audit/shadow_ai_scans.jsonl`:

```json
{
  "schema_version": "v1",
  "event_type": "DISCOVERY_SCAN",
  "scan_id": "a1b2c3d4",
  "timestamp": "2026-04-18T21:00:00Z",
  "scan_root": "/home/user/projects",
  "summary": {
    "covered": 5,
    "broken_hooks": 1,
    "unguarded": 2,
    "posture_maturity_score": 72.5,
    "high_findings": 2,
    "mcp_servers": 4
  },
  "agents": [...],
  "coverage_map": [
    {"repo_path": "...", "agent": "Claude", "status": "COVERED", "hook_healthy": true, ...}
  ],
  "mcp_servers": [
    {"name": "bash-runner", "capability_tier": "exec", "trust": false, ...}
  ],
  "findings": [...]
}
```

### Dashboard

The **AI Posture & Discovery** tab reads `shadow_ai_scans.jsonl` and renders:

- **Metric row** — IDEs, Agents, Pairs, Covered, Broken, Unguarded, MCP Servers, High/Medium findings, Maturity %
- **Posture Score Trend** — Plotly line chart of maturity score across all historical scans
- **Scan Drift panel** — score delta vs previous scan, lists lost/gained protection and new agents
- **Findings** — expandable cards sorted by severity; HIGH findings auto-expanded
- **Coverage Map** — sortable table with `BROKEN_HOOK` highlighted in red, hook health column
- **Agent Inventory** — split into IDE / CLI / CI/CD Pipeline / Extension categories
- **MCP Surface** — table with Capability Risk column; exec-tier servers flagged in red, network-tier in amber
- **Full-page Markdown export** — download button exports every section above as a structured report
