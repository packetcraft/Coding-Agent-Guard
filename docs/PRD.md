# Product Requirements Document (PRD): Coding Agent Guard

## 1. Executive Summary
**Coding Agent Guard** is a dual-mode security primitive designed to provide an **"Active Defense"** layer and **"Postural Intelligence"** for autonomous AI coding agents (e.g., Claude Code, Gemini CLI, Antigravity, VS Code). It intercepts tool executions in real-time and provides a continuous, queryable inventory of the AI attack surface on a machine.

## 2. Problem Statement
Autonomous agents possess the capability to execute shell commands and modify files. While powerful, this introduces significant risks:
- **Accidental Destruction**: An agent might misunderstood a request and run `rm -rf /`.
- **Malicious Injection**: Untrusted code or documentation read by the agent could contain "Prompt Injections" that trick the agent into stealing secrets.
- **Data Exfiltration**: An agent could be manipulated into sending private SSH keys or `.env` files to an external server.

Existing security measures are often "Passive" (logs only). **Coding Agent Guard** provides an "Active" barrier that blocks dangerous actions before they occur.

## 3. Goals & Objectives
- **Standalone Portability**: Decouple the guard from the research workbench into a lightweight, installable package.
- **Real-time Enforcement**: Provide sub-second latency for security verdicts.
- **Multi-Agent Compatibility**: Support major agentic CLIs and IDE-based agents through a unified adapter and discovery framework.
- **Privacy First**: Perform all classifications locally using Ollama to ensure no code or secrets leave the user's machine.
- **Postural Intelligence (Shadow AI)**: Provide IT/CISO teams with visibility into all installed agents, configured MCP servers, and unguarded repositories.
- **Human-in-the-Loop**: Enable a path toward interactive approval for high-risk actions.

## 4. Target Audience
- **Individual Developers**: Using AI agents for local coding.
- **Enterprise Security Teams**: Seeking to provide a "paved path" for safe AI agent adoption.
- **Agent Developers**: Needing a standardized security hook for their tools.

## 5. Functional Requirements (V1 — Delivered)

### Active Defense
- **Tool-Call Interception**: Capture `PreToolUse` (input) and `PostToolUse` (output) hooks for Claude Code and Gemini CLI.
- **LLM Classification**: Use local models (e.g., `qwen2.5:1.5b`) to evaluate intent.
- **Fast-path Allowlisting**: Regex-based bypass for known safe commands (`git status`, `ls`).
- **Secret Redaction**: Automatic masking of API keys and credentials in audit logs.
- **Protected Paths**: Hard-block modifications to sensitive system or configuration files.
- **Structured Auditing**: Generate JSONL logs for every action for forensic review.

### Postural Intelligence (Shadow AI Discovery — v1.2.0)
- **Wide Agent Detection**: 17 installation surfaces — CLI tools (Ollama, Open Interpreter, Aider), IDEs (VS Code, Zed, Cursor, Windsurf, Antigravity, LM Studio), extensions (Copilot, Continue.dev, Amazon Q, Cody), desktop apps (Claude Desktop), and CI/CD pipeline agents (GitHub Actions).
- **Hook Liveness Validation**: `BROKEN_HOOK` status — detects guard hooks whose binary is missing, preventing false sense of coverage.
- **MCP Capability Risk Scoring**: Classifies each MCP server into `exec` / `network` / `write-local` / `read-only` tiers; surfaces exec- and network-tier servers as findings.
- **Memory File Secrets Scan**: Scans agent memory files (`~/.claude/`, `~/.gemini/`, brain sessions) for credential patterns that could be exfiltrated via prompt injection.
- **CI/CD Pipeline Agent Detection**: Scans `.github/workflows/*.yml` for AI agent action references; generates `CICD_AGENT_UNGUARDED` findings for unguarded pipelines.
- **Posture Drift (`--diff`)**: Compares scans over time to surface new agents, lost protections, new MCP servers, and score delta.
- **Remediation Auto-fix (`--fix`)**: Interactively writes guard hooks into unguarded Claude repos with confirmation before any file is modified.
- **Posture Maturity Scoring**: Heuristic 0–100% grade; historical trend chart in dashboard.
- **Full-page Report Export**: Dashboard exports every section of the AI Posture & Discovery tab as a structured Markdown report.

### Security Dashboard
- **AI Posture & Discovery tab**: Agent inventory, coverage map (with `BROKEN_HOOK` highlighting), MCP surface with capability risk tiers, findings, posture score trend, and scan drift panel.
- **Live Feed**: Auto-refreshing view of current hook events.
- **Forensics & Logs**: Filterable audit explorer with keyword search.
- **Analytics**: Block rate over time, verdict distribution, latency percentiles (P50/P95/P99).

## 6. Roadmap (V2 — Future)
- **Universal Shell Observation**: Audit-only shell wrappers to capture commands from any agent process regardless of native hook support.
- **Interactive Approval UI**: Pause execution for human review via a lightweight UI (Streamlit).
- **Runtime Sandbox**: Automatically wrap shell commands in Docker/nsjail.
- **Static Analysis Guard**: Intercept file writes to run `bandit` or `eslint-plugin-security`.
- **MCP Tool Enumeration**: Live introspection of local MCP servers to enumerate exposed tool schemas.
- **Supply Chain Guard**: Typosquatting and malicious package detection for `pip`/`npm` installs by agents.

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

