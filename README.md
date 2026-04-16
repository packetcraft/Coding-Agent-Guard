# Coding Agent Guard 🛡️

**Coding Agent Guard** is a standalone security primitive for autonomous AI coding agents. It intercepts every tool call and output, classifying them with a local LLM guard (via Ollama) to detect and block destructive commands, unauthorized exfiltration, and prompt injection attacks — before they execute.

## 🌟 Key Features

- **Action Guard**: Evaluates tool calls (`Bash`, `Write`, `Edit`, `WebFetch`, MCP tools) against security policies using a local LLM before execution.
- **Injection Guard**: Scans tool outputs (file reads, web fetches) for prompt injection and instruction-override attacks after execution.
- **Secret Redaction**: Automatically redacts API keys, credentials, and sensitive tokens from audit logs before they are written to disk.
- **Smart Allowlist**: Fast-path bypass for common read-only commands (`ls`, `git status`, etc.) to minimize latency overhead.
- **Protected Paths**: Hard-blocks any attempt by an agent to modify the guard's own configuration or hook files.
- **Audit Logging**: Detailed JSONL logs of every tool call, verdict, latency, and redaction count, written per session.
- **Multi-Agent Support**: Native hook adapters for Claude Code and Gemini CLI.
- **Security Dashboard**: Streamlit UI for real-time monitoring and historical audit exploration with filtering by agent, session, tool, and verdict.

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
- Guard model pulled:
  ```bash
  ollama pull qwen2.5:1.5b
  ```
  *(Low-VRAM fallback: `tinyllama`)*

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/packetcraft/Coding-Agent-Guard.git
   cd Coding-Agent-Guard
   ```

2. Create a virtual environment (optional but recommended):

   **macOS / Linux:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   **Windows — Git Bash / MINGW64:**
   ```bash
   python -m venv venv
   source venv/Scripts/activate
   ```

   **Windows — PowerShell:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. Install the package:
   ```bash
   pip install -e .
   ```
   This registers the `coding-agent-guard` command in your environment.

### Hook Installation

The guard works by registering as a pre/post-tool hook in the target repository's agent settings. Run the installer from the `Coding-Agent-Guard` root, pointing it at the repo you want to protect:

```bash
python install_hooks.py /path/to/your-repo
```

This creates or **merges** `.claude/settings.json` and `.gemini/settings.json` in the target repo. Existing hook entries are preserved; the guard's entries are appended only if not already present. A summary is printed showing what was added vs. skipped.

```
[Claude] Updated (added 6, skipped 0 already-present): /path/to/your-repo/.claude/settings.json
[Gemini] Updated (added 2, skipped 0 already-present): /path/to/your-repo/.gemini/settings.json
```

**`--force` flag:** To overwrite existing settings completely instead of merging:
```bash
python install_hooks.py /path/to/your-repo --force
```

#### Manual Setup

If you prefer to configure hooks by hand, copy the templates from `agent_configs/`:

**Claude Code** — copy to `.claude/settings.json` in the target repo:
```bash
# macOS / Linux
cp /path/to/Coding-Agent-Guard/agent_configs/claude.settings.template.json .claude/settings.json

# Windows PowerShell
Copy-Item C:\path\to\Coding-Agent-Guard\agent_configs\claude.settings.template.json .claude\settings.json
```

**Gemini CLI** — copy to `.gemini/settings.json` in the target repo:
```bash
# macOS / Linux
cp /path/to/Coding-Agent-Guard/agent_configs/gemini_settings.template.json .gemini/settings.json

# Windows PowerShell
Copy-Item C:\path\to\Coding-Agent-Guard\agent_configs\gemini_settings.template.json .gemini\settings.json
```

> The templates use `"command": "coding-agent-guard"` which requires a global install (`pip install -e .`). If you installed into a venv, use the automated installer instead — it writes the absolute path to the venv executable.

### Security Dashboard

```bash
python dashboard.py
```

The dashboard reads from the `audit/` directory and provides:

- **Live Feed**: Auto-refreshing view of current tool calls and verdicts.
- **Audit Explorer**: Filterable history of all security events (filter by agent, session, tool, verdict, or keyword).
- **Security Charts**: Block rates, tool usage breakdown, and latency distribution.

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
