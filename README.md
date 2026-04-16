# Coding Agent Guard 🛡️

**Coding Agent Guard** is a standalone security primitive designed to provide deep security for autonomous agents that write, execute, and deploy code. It acts as an "Active Defense System" by intercepting tool calls and outputs to detect and block malicious or dangerous actions.

Originally part of the `llm-sec-workbench`, it has been carved out to provide a lightweight, portable, and production-ready security layer for local systems.

## 🌟 Key Features

- **Action Guard**: Evaluates tool execution payloads (like `bash`, `write_file`) against security policies using local LLMs (via Ollama).
- **Injection Guard**: Scans tool outputs (file reads, web fetches) for prompt injection or instruction override attacks.
- **Secret Redaction**: Automatically redacts API keys, credentials, and sensitive tokens from audit logs.
- **Smart Allowlist**: Fast-path for common read-only commands (e.g., `ls`, `git status`) to minimize latency.
- **Protected Paths**: Prevents agents from modifying critical configuration files or the guard itself.
- **Telemetry & Auditing**: Detailed JSONL logs of every tool call, verdict, and latency for security review.
- **Multi-Agent Support**: Native adapters for Claude Code and Gemini CLI.
- **Security Dashboard**: Standalone Streamlit UI for real-time monitoring and audit exploration.

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- [Ollama](https://ollama.com/) (installed and running)
- Recommended Model: `qwen2.5:1.5b`
  ```bash
  ollama pull qwen2.5:1.5b
  ```

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/packetcraft/Coding-Agent-Guard.git
   cd Coding-Agent-Guard
   ```

2. Create a virtual environment (optional but recommended):
   - **macOS / Linux**:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```
   - **Windows (Git Bash / MINGW64)**:
     ```bash
     python -m venv venv
     source venv/Scripts/activate
     ```
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```

3. Install the package in editable mode:
   ```bash
   pip install -e .
   ```
   *This makes the `coding-agent-guard` command available globally in your environment.*

### Usage

The guard can be added to **any** repository. We provide template settings files in the `agent_configs/` directory.

#### Claude Code

To protect a repository, navigate to its root and copy the template:

- **macOS / Linux / Windows (PowerShell)**:
  ```bash
  mkdir -p .claude
  cp /path/to/Coding-Agent-Guard/agent_configs/claude.settings.template.json .claude/settings.json
  ```

#### Gemini CLI

To protect a repository, navigate to its root and copy the template:

- **macOS / Linux / Windows (PowerShell)**:
  ```bash
  mkdir -p .gemini
  cp /path/to/Coding-Agent-Guard/agent_configs/gemini_settings.template.json .gemini/settings.json
  ```

### Security Dashboard

To monitor your agent's activity and audit past sessions, launch the real-time dashboard:

```bash
# From the Coding-Agent-Guard root
python dashboard.py
```

The dashboard provides:
- **Live Feed**: Auto-refreshing view of current tool calls and verdicts.
- **Audit Explorer**: Filterable historical view of all security events.
- **Security Dashboard**: Statistical charts on block rates, tool usage, and latency.

## ⚙️ Configuration

Security rules and model settings are decoupled into YAML files in the `coding_agent_guard/rules/` directory:

- `config.yaml`: General settings (model selection, timeout, audit path).
- `patterns.yaml`: Regex patterns for injections and protected file paths.

## 🗺️ Roadmap (V2)

- [ ] **Static Analysis Guard**: Integrated `bandit` and `eslint` scanning for proposed code changes.
- [ ] **Runtime Sandbox**: Automatic containerization of bash commands.
- [ ] **Supply Chain Guard**: Typosquatting and malicious package detection for `pip`/`npm`.
- [ ] **Human-in-the-Loop (HITL)**: Interactive approval UI for high-risk actions.

## 📄 License

MIT
