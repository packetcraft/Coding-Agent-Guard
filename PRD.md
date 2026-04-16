# Product Requirements Document (PRD): Coding Agent Guard

## 1. Executive Summary
**Coding Agent Guard** is a standalone security primitive designed to provide an "Active Defense" layer for autonomous AI coding agents (e.g., Claude Code, Gemini CLI, GitHub Copilot CLI). It intercepts tool executions and outputs in real-time to prevent destructive operations, unauthorized data exfiltration, and prompt injection attacks.

## 2. Problem Statement
Autonomous agents possess the capability to execute shell commands and modify files. While powerful, this introduces significant risks:
- **Accidental Destruction**: An agent might misunderstood a request and run `rm -rf /`.
- **Malicious Injection**: Untrusted code or documentation read by the agent could contain "Prompt Injections" that trick the agent into stealing secrets.
- **Data Exfiltration**: An agent could be manipulated into sending private SSH keys or `.env` files to an external server.

Existing security measures are often "Passive" (logs only). **Coding Agent Guard** provides an "Active" barrier that blocks dangerous actions before they occur.

## 3. Goals & Objectives
- **Standalone Portability**: Decouple the guard from the research workbench into a lightweight, installable package.
- **Real-time Enforcement**: Provide sub-second latency for security verdicts.
- **Multi-Agent Compatibility**: Support major agentic CLIs through a unified adapter interface.
- **Privacy First**: Perform all classifications locally using Ollama to ensure no code or secrets leave the user's machine.
- **Human-in-the-Loop**: Enable a path toward interactive approval for high-risk actions.

## 4. Target Audience
- **Individual Developers**: Using AI agents for local coding.
- **Enterprise Security Teams**: Seeking to provide a "paved path" for safe AI agent adoption.
- **Agent Developers**: Needing a standardized security hook for their tools.

## 5. Functional Requirements (V1 - Current)
- **Tool-Call Interception**: Capture `PreToolUse` (input) and `PostToolUse` (output) hooks.
- **LLM Classification**: Use local models (e.g., `qwen2.5:1.5b`) to evaluate intent.
- **Fast-path Allowlisting**: Regex-based bypass for known safe commands (`git status`, `ls`).
- **Secret Redaction**: Automatic masking of API keys and credentials in audit logs.
- **Protected Paths**: Hard-block modifications to sensitive system or configuration files.
- **Structured Auditing**: Generate JSONL logs for every action for forensic review.

## 6. Roadmap (V2 - Future)
- **Static Analysis Guard**: Intercept file writes to run `bandit` or `eslint-plugin-security`.
- **Runtime Sandbox**: Automatically wrap shell commands in Docker/nsjail.
- **Supply Chain Guard**: Detect malicious `pip`/`npm` package installations.
- **Interactive Approval UI**: Pause execution for human review via a lightweight UI (Streamlit).

## 8. Technical Constraints
- **Language**: Python 3.9+
- **Inference**: Ollama (Local only)
- **Format**: JSON-based stdin/stdout for hook communication.
- **Latency Target**: < 2 seconds for LLM-based verdicts; < 50ms for regex-based verdicts.

## 9. Architectural Decisions: Namespace Protection
The repository employs a nested package structure (`coding_agent_guard/core`, etc.) to ensure **Namespace Protection** when installed globally via `pip`.

### 9.1 Reasoning
- **Global Compatibility**: By namespacing the modules, we prevent "import collisions" with other local projects. A user can work in a project that has its own `core/` or `utils/` folder without Python confusing them with the guard's internals.
- **Production Standard**: This follows the "Src Layout" pattern (modified for local development), which is a senior engineering standard for Python packages to ensure that tests and external scripts are truly testing the installed package rather than a local folder.
- **Developer Experience**: It allows the `coding-agent-guard` CLI command to be truly global and reliable across different workspace environments.

