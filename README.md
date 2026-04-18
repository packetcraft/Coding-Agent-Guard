# Coding Agent Guard 🛡️

**Coding Agent Guard** is a standalone security primitive for autonomous AI coding agents. It intercepts every tool call and output, classifying them with a local LLM guard (via Ollama) to detect and block destructive commands, unauthorized exfiltration, and prompt injection attacks — before they execute.

## 🌟 Key Features

- **Action Guard**: Evaluates tool calls (`Bash`, `Write`, `Edit`, `WebFetch`, MCP tools) against security policies using a local LLM before execution.
- **Injection Guard**: Scans tool outputs (file reads, web fetches) for prompt injection and instruction-override attacks after execution.
- **Secret Redaction**: Automatically redacts API keys, credentials, and sensitive tokens from audit logs before they are written to disk.
- **Smart Allowlist**: Fast-path bypass for common read-only commands (`ls`, `git status`, etc.) to minimize latency overhead.
- **Protected Paths**: Hard-blocks any attempt by an agent to modify the guard's own configuration or hook files.
- **Audit Logging**: Detailed JSONL logs of every tool call, verdict, latency, and redaction count, written per session.
- **Multi-Agent Support**: Native hook adapters for Claude Code and Gemini CLI; specialized observation for Antigravity, VS Code, and Zed.
- **Shadow AI Discovery**: Full-machine posture scan across 17 agent installation surfaces — CLI tools, IDEs, extensions, desktop apps, and CI/CD pipelines.
- **Hook Liveness Validation**: Detects `BROKEN_HOOK` status — repos that appear covered but whose guard binary is missing, leaving tool calls uninspected.
- **MCP Capability Risk Scoring**: Classifies every MCP server into an exec / network / write-local / read-only risk tier and flags dangerous servers as findings.
- **Memory File Secrets Scan**: Detects credential patterns in agent memory files (`~/.claude/`, `~/.gemini/`) that could be exfiltrated via prompt injection.
- **Posture Drift**: `--diff` flag compares scans over time to surface new agents, lost protections, and new MCP servers.
- **Remediation Auto-fix**: `--fix` flag interactively writes guard hooks into unguarded repos.
- **External Brain Discovery**: Identifies active agents via "Digital Exhaust" in home directories, even if project artifacts are removed.
- **Security Dashboard**: Premium Streamlit UI with dedicated tabs for **Live Feed**, **Audit Explorer**, **Analytics**, and **AI Posture & Discovery**. Includes posture score trend chart and full-page Markdown export.

## ⚠️ Audit-Only Mode (Default)

**The guard ships with `audit_only: true`.** In this mode the guard classifies every tool call and logs the verdict, but **never blocks** — the agent is always allowed to proceed. Detected threats are recorded as `BLOCK_AUDITED` in the audit log.

This is intentional for initial setup: you can observe what the guard would have blocked before enabling enforcement.

**To enable enforcement**, open `coding_agent_guard/rules/config.yaml` and set:

```yaml
audit_only: false
```

In enforcement mode, a `BLOCK` verdict causes the hook to exit with code `2`, which stops the agent from executing the tool call.

> When a new session starts in audit-only mode, the guard emits a warning to stderr so it's visible in the agent's terminal:
> `[coding-agent-guard] WARNING: audit_only=true — guard is logging but NOT blocking.`

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- [Ollama](https://ollama.com/) installed and running

### Quick Setup (recommended)

Clone the repo and run the setup script — it handles everything automatically:

```bash
git clone https://github.com/packetcraft/Coding-Agent-Guard.git
cd Coding-Agent-Guard
```

**macOS / Linux / Git Bash:**
```bash
./setup.sh
```

**Windows (CMD):**
```bat
setup.bat
```

The script runs 6 steps and prints progress:

```
[ 1/6 ] Checking Python...         OK -- Python 3.12.10
[ 2/6 ] Checking Ollama...         OK -- ollama version 0.x.x
[ 3/6 ] Virtual environment...     OK -- venv created
[ 4/6 ] Installing package...      OK -- coding-agent-guard installed
[ 5/6 ] Guard model...             Pulling qwen2.5:1.5b...  OK
[ 6/6 ] Installing guard hooks...  [Claude] added 6  [Gemini] added 2
```

#### Repair / reinstall

If the venv is broken or you want a clean reinstall:

```bash
./setup.sh --repair   # macOS / Linux / Git Bash
setup.bat /repair     # Windows CMD
```

This wipes the venv, recreates it, reinstalls the package, re-pulls the model, and reinstalls hooks.

---

### Starting the Dashboard

```bash
./start.sh    # macOS / Linux / Git Bash
start.bat     # Windows CMD
```

Opens the Streamlit dashboard at **http://localhost:8501** with five tabs:

- **📘 System Blueprint** — architecture overview, hook interception strategy, and enforcement modes
- **📡 Live Feed** — auto-refreshing view of current tool calls and verdicts
- **🔍 Forensics & Logs** — filterable history of all security events with keyword search
- **📊 Dashboard** — analytics: block rate over time, verdict distribution, latency P50/P95/P99
- **🛡️ AI Posture & Discovery** — posture scan: agent inventory, hook coverage map (with `BROKEN_HOOK` detection), MCP surface with capability risk tiers, security findings, posture score trend chart, and scan drift panel. Exportable as a full-page Markdown report.

The UI features a premium **Tokyo Night-inspired dark theme** ported from the LLM Security Workbench for a unified professional experience.

---

### Manual Installation

If you prefer step-by-step control:

1. Clone the repository:
   ```bash
   git clone https://github.com/packetcraft/Coding-Agent-Guard.git
   cd Coding-Agent-Guard
   ```

2. Create and activate a virtual environment:

   **macOS / Linux:**
   ```bash
   python3 -m venv venv && source venv/bin/activate
   ```

   **Windows — Git Bash:**
   ```bash
   rm -rf venv
   python -m venv venv && source venv/Scripts/activate
   ```

   **Windows — PowerShell:**
   ```powershell
   python -m venv venv; .\venv\Scripts\Activate.ps1
   ```

3. Install the package:
   ```bash
   pip install -e .
   ```

4. Pull the guard model:
   ```bash
   ollama pull qwen2.5:1.5b
   ```
   *(Low-VRAM fallback: `tinyllama`)*

5. Install hooks (see Hook Installation below).

---

### Hook Installation

The guard works by registering as a pre/post-tool hook in the target repository's agent settings. Run the installer from the `Coding-Agent-Guard` root, pointing it at the repo you want to protect:

```bash
python install_hooks.py /path/to/your-repo
```

This creates or **merges** `.claude/settings.json` and `.gemini/settings.json` in the target repo. Existing hook entries are preserved; the guard's entries are appended only if not already present.

```
[Claude] Updated (added 6, skipped 0 already-present): /path/to/your-repo/.claude/settings.json
[Gemini] Updated (added 2, skipped 0 already-present): /path/to/your-repo/.gemini/settings.json
```

**`--force` flag:** Overwrite existing settings completely instead of merging:
```bash
python install_hooks.py /path/to/your-repo --force
```

#### Manual Hook Setup

If you prefer to configure hooks by hand, copy the templates from `agent_configs/`:

```bash
# macOS / Linux
cp /path/to/Coding-Agent-Guard/agent_configs/claude.settings.template.json .claude/settings.json
cp /path/to/Coding-Agent-Guard/agent_configs/gemini_settings.template.json .gemini/settings.json

# Windows PowerShell
Copy-Item C:\path\to\Coding-Agent-Guard\agent_configs\claude.settings.template.json .claude\settings.json
Copy-Item C:\path\to\Coding-Agent-Guard\agent_configs\gemini_settings.template.json .gemini\settings.json
```

> The templates use `"command": "coding-agent-guard"` which requires the venv to be active. If the venv may not always be active, use the automated installer — it writes the absolute path to the venv executable.

### 🐧 Universal Shell Guard & Antigravity
For IDE-based agents (like Antigravity) that don't support native hooks, or to passively audit any shell-based agent, use the `shell_guard` adapter:

```bash
python -m coding_agent_guard.adapters.shell_guard <command>
```

**Example: Guarding Antigravity**
```bash
python -m coding_agent_guard.adapters.shell_guard antigravity
```
This wraps the agent process, logging every shell command it executes to the audit trail while allowing them to run in AUDIT mode.

### 📡 Shadow AI Posture Scan

Run a discovery scan to audit all AI agents, hook coverage, MCP servers, and trust settings on the machine:

```bash
coding-agent-guard shadow-ai
```

Options:
```bash
coding-agent-guard shadow-ai --root /path/to/projects   # scan a specific directory
coding-agent-guard shadow-ai --output json               # JSON output for SIEM/export
coding-agent-guard shadow-ai --no-audit                  # skip writing to audit log
coding-agent-guard shadow-ai --diff                      # compare against previous scan (posture drift)
coding-agent-guard shadow-ai --fix                       # interactively write guard hooks for unguarded repos
```

Results are written to `audit/shadow_ai_scans.jsonl` and rendered in the **AI Posture & Discovery** dashboard tab.

#### What the scan detects

**Agent Detection** — 17 installation surfaces including:
- IDEs: VS Code, Zed, Cursor, Windsurf / Codeium, Antigravity
- CLI agents: Claude Code, Gemini CLI, Aider, Ollama, Open Interpreter
- Extensions: GitHub Copilot, Continue.dev, Amazon Q, Cody, GitHub Copilot CLI
- Desktop apps: Claude Desktop, LM Studio
- **CI/CD pipelines**: scans `.github/workflows/*.yml` for AI agent action references (Claude GitHub Action, Copilot Workspace, Devin, etc.)

**Coverage Analysis** — per (repo × agent) pair:

| Status | Meaning |
|---|---|
| `COVERED` | Guard hook registered and binary verified alive |
| `BROKEN_HOOK` | Guard hook registered but binary missing — appears covered, actually unprotected |
| `SHADOW_HOOK` | Hook slot occupied by a non-guard command |
| `ARTIFACT_ONLY` | Agent detected via in-repo artifacts (passive monitoring only) |
| `EXTERNAL_BRAIN` | Agent detected via home-dir brain session |
| `UNGUARDED` | No hooks or detection signals found |

**Security Findings** — 9 finding categories:

| Category | Severity |
|---|---|
| `BROKEN_HOOK` | HIGH |
| `SECRET_IN_AGENT_MEMORY` | HIGH |
| `REMOTE_MCP_TRUST_TRUE` | HIGH |
| `DANGEROUS_MCP_CAPABILITY_EXEC` | HIGH |
| `DANGEROUS_MCP_CAPABILITY_NETWORK` | MEDIUM |
| `CICD_AGENT_UNGUARDED` | MEDIUM |
| `UNGUARDED_AGENT` | MEDIUM |
| `API_KEY_IN_ENV` / `API_KEY_IN_FILE` | MEDIUM |
| `SHADOW_HOOK` / `ORPHANED_HOOK` | LOW |

**MCP Capability Risk Scoring** — each MCP server is classified into a tier:
- `exec` — can run code or shell commands (highest risk)
- `network` — can make outbound requests
- `write-local` — can modify files or data
- `read-only` — no destructive capability

**Posture Drift** (`--diff`) — compares the latest scan to the previous one and surfaces:
- New agents installed since last scan
- Repos that lost or gained protection
- New MCP servers added without review
- Posture score delta

**Remediation Auto-fix** (`--fix`) — for each unguarded Claude repo, previews the hook block that will be written and applies it after interactive confirmation.

## ⚙️ Configuration

Edit `coding_agent_guard/rules/config.yaml` to tune the guard's behavior:

| Setting | Default | Description |
|---|---|---|
| `guard_model` | `qwen2.5:1.5b` | Ollama model used for classification. Must be pulled first. |
| `guard_timeout_ms` | `5000` | Hard timeout in ms. The guard fails open on timeout — the tool call is allowed. |
| `audit_path` | `./audit` | Path (relative to the protected repo root) where JSONL audit logs are written. |
| `allowlist_enabled` | `true` | Fast-path bypass for read-only commands. Disable to send everything through the LLM. |
| `allowlist_patterns` | `[]` | Additional regex patterns to allowlist beyond the built-in read-only set. |
| `audit_only` | `true` | **When `true`: logs only, never blocks.** Set to `false` to enable enforcement. |

Edit `coding_agent_guard/rules/patterns.yaml` to customize:

- `ipi_blocklist`: Regex patterns that trigger an instant `BLOCK_AUDITED` on tool output (fast-path, no LLM call).
- `protected_paths`: File paths that the guard will hard-block any `Write`/`Edit` attempt against.

## Verdict Reference

| Verdict | Meaning |
|---|---|
| `ALLOW` | Tool call cleared by the guard. |
| `BLOCK` | Tool call blocked (only possible when `audit_only: false`). |
| `BLOCK_AUDITED` | Guard would have blocked, but `audit_only: true` — tool call was allowed. |
| `ALLOWLISTED` | Matched the read-only allowlist; bypassed LLM classification. |
| `ERROR` | Guard model timed out or failed; tool call was allowed (fail-open). |

## 🗺️ Roadmap (V2)

- [ ] **Static Analysis Guard**: Integrated `bandit` and `eslint` scanning for proposed code changes.
- [ ] **Runtime Sandbox**: Automatic containerization of bash commands.
- [ ] **Supply Chain Guard**: Typosquatting and malicious package detection for `pip`/`npm`.
- [ ] **Human-in-the-Loop (HITL)**: Interactive approval UI for high-risk actions.

## 📄 License

MIT
