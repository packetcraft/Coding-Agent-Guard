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
   git clone https://github.com/your-repo/Coding-Agent-Guard.git
   cd Coding-Agent-Guard
   ```

2. Install the package globally (recommended):
   ```bash
   pip install -e .
   ```
   *This makes the `coding-agent-guard` command available from any directory.*

### Usage

The guard can be added to **any** repository you are working in. We provide template settings files in the `agent_configs/` directory for quick setup.

#### Claude Code

To protect a repository, navigate to it and copy the template:

```bash
# In the repository you want to protect
mkdir -p .claude
cp /path/to/Coding-Agent-Guard/agent_configs/claude.settings.template.json .claude/settings.json
```

#### Gemini CLI

To protect a repository, navigate to it and copy the template:

```bash
# In the repository you want to protect
mkdir -p .gemini
cp /path/to/Coding-Agent-Guard/agent_configs/gemini_settings.template.json .gemini/settings.json
```

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
