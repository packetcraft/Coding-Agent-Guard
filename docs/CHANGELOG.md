# Changelog

All notable changes to the **Coding Agent Guard** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-04-23

### Added

**Guard Enhancements & Posture Patrol — Active Defense Update**

#### What Was Implemented

| # | Feature | Files Changed |
|---|---------|--------------|
| 1 | **Daily Patrol** (`guard patrol`) | `patrol.py` — `PatrolEngine`, background loop, drift detection |
| 2 | **Static Analysis Guard** (`guard scan`) | `static_scanner.py` — 24 rules (Trojan, Obfuscation, Secrets, Shell Exec) |
| 3 | **Visual Health Dashboard** | `dashboard.py` — Maturity Gauge, Guardy Mascot, Patrol Status banner |
| 4 | **Agent & Skill Attribution** | `guard.py`, `dashboard.py` — `skill_id` tracking for MCP tools |
| 5 | **Action Guard Fast-Path** | `guard.py` — Static scan integration before LLM classification |

#### Test Plan

**1. Daily Patrol (`guard patrol`)**
```bash
coding-agent-guard patrol run
coding-agent-guard patrol status
```
Verify: Patrol runs discovery, compares with baseline, and logs results to `audit/patrol_history.jsonl`.

**2. Static Analysis Guard (`guard scan`)**
```bash
coding-agent-guard scan . --recursive
```
Verify: Detects malicious patterns (e.g. `rm -rf /`, AWS keys) with 24 specialized rules.

**3. Visual Health Checkup**
Navigate to **AI Posture & Discovery** tab. Verify:
- Plotly Maturity Gauge renders correctly.
- Guardy Mascot (🚨, ⚠️, ✅) updates based on score.
- Active Patrol status banner appears at the top.

**4. Skill Attribution**
Run an agent tool call (e.g. via an MCP server). Verify:
- Live Feed and Audit Explorer show the `skill_id` (e.g. server name).

---

## [1.2.0] - 2026-04-18

### Added

**AI Posture & Discovery — Major Enhancements**

#### What Was Implemented

| # | Feature | Files Changed |
|---|---------|--------------|
| 1 | **Temporal Posture Drift** (`--diff`) | `scanner.py` — `diff_scans()`, `load_all_scans()`, CLI flag |
| 2 | **Hook Liveness Validation** (`BROKEN_HOOK`) | `gap_analyzer.py` — `_check_hook_liveness()`, `trust_analyzer.py` — BROKEN_HOOK finding |
| 3 | **Wider Agent Detection** | `agents.py` — Ollama, LM Studio, Open Interpreter, Copilot CLI |
| 4 | **CI/CD Pipeline Agents** | `agents.py` — `detect_cicd_agents()`, `trust_analyzer.py` — CICD_AGENT_UNGUARDED finding |
| 5 | **MCP Capability Risk Scoring** | `mcp_inventory.py` — `_classify_capability_tier()`, `trust_analyzer.py` — DANGEROUS_MCP_CAPABILITY finding |
| 6 | **Sensitive Data in Memory Files** | `trust_analyzer.py` — `_check_memory_files_secrets()`, HIGH severity finding |
| 7 | **Remediation Automation** (`--fix`) | `scanner.py` — `_apply_fix()`, interactive hook writer |
| 8 | **Posture Score Trend + Scan Diff** | `dashboard.py` — Plotly trend chart, drift panel, BROKEN_HOOK colors, capability tier column |

#### Test Plan

**1. Temporal Posture Drift (`--diff`)**
```bash
coding-agent-guard shadow-ai
coding-agent-guard shadow-ai --diff
```
Verify: Shows "No changes" on identical runs. Edit a `.claude/settings.json` to remove a hook between runs — the diff should show the repo under "Lost protection".

**2. Hook Liveness Validation (`BROKEN_HOOK`)**
```bash
echo '{"hooks":{"PreToolUse":[{"matcher":".*","hooks":[{"type":"command","command":"/nonexistent/coding-agent-guard pre-tool-use"}]}]}}' > /tmp/test-repo/.claude/settings.json
coding-agent-guard shadow-ai --root /tmp
```
Verify: Repo appears as `BROKEN_HOOK` (not `COVERED`) with a HIGH severity `BROKEN_HOOK` finding.

**3. Wider Agent Detection (Ollama, LM Studio, etc.)**
```bash
ollama --version  # confirm installed
coding-agent-guard shadow-ai --output json | python -m json.tool | grep -i "ollama"
```
Verify: Ollama appears in `agents` array with `install_method: "path"` or `"app"`.

**4. CI/CD Pipeline Agent Detection**
```bash
mkdir -p /tmp/test-cicd/.github/workflows
echo "uses: anthropic-ai/claude-github-action@v1" > /tmp/test-cicd/.github/workflows/ai.yml
coding-agent-guard shadow-ai --root /tmp/test-cicd --output json | python -m json.tool | grep -i "github action"
```
Verify: `"Claude (GitHub Action)"` appears in agents with `install_method: "ci_pipeline"`, and a `CICD_AGENT_UNGUARDED` MEDIUM finding is emitted.

**5. MCP Capability Risk Scoring**
```bash
# Add an exec-tier MCP server to ~/.claude/settings.json
# e.g. {"mcpServers": {"bash-exec": {"command": "bash-mcp-server"}}}
coding-agent-guard shadow-ai --output json | python -m json.tool | grep -A2 "capability_tier"
```
Verify: `"bash-exec"` gets `capability_tier: "exec"`, and a `DANGEROUS_MCP_CAPABILITY_EXEC` HIGH finding appears.

**6. Sensitive Data in Memory Files**
```bash
echo "sk-ant-test12345678901234567890" >> ~/.claude/CLAUDE.md
coding-agent-guard shadow-ai --output json | python -m json.tool | grep "SECRET_IN_AGENT_MEMORY"
# Clean up after test
```
Verify: `SECRET_IN_AGENT_MEMORY` HIGH finding appears pointing to `~/.claude/CLAUDE.md`.

**7. Remediation Auto-fix (`--fix`)**
```bash
mkdir -p /tmp/test-unguarded/.claude
echo '{}' > /tmp/test-unguarded/.claude/settings.json && git init /tmp/test-unguarded
coding-agent-guard shadow-ai --root /tmp/test-unguarded --fix
cat /tmp/test-unguarded/.claude/settings.json
```
Verify: `settings.json` now contains `hooks.PreToolUse` and `hooks.PostToolUse` entries with `coding-agent-guard` commands.

**8. Posture Score Trend + Dashboard**
```bash
# Run 3+ scans to build history
coding-agent-guard shadow-ai && coding-agent-guard shadow-ai && coding-agent-guard shadow-ai
streamlit run coding_agent_guard/ui/dashboard.py
```
Navigate to **AI Posture & Discovery** tab. Verify:
- "Posture Maturity Score — Trend" line chart appears (requires ≥ 2 scans in history)
- "Drift vs Previous Scan" panel shows score delta and highlights changes
- MCP table has a "Capability Risk" column
- BROKEN_HOOK repos appear in bright red in the coverage table

---

## [1.1.2] - 2026-04-18

### Added
- **Report Export**: Users can now export the **Security Analytics Dashboard** and **Shadow AI Discovery** results as well-formatted Markdown reports for auditing and compliance.
- **Categorized Inventory**: The discovery UI now separates detected tools into **AI-Powered IDEs** and **Autonomous Agents** for better information hierarchy.

## [1.1.1] - 2026-04-18

### Added
- **Expanded Agent Support**: The Shadow AI discovery engine now detects **VS Code**, **Zed**, and **Antigravity** IDEs.
- **Improved Configuration Crawling**: 
    - Support for **Zed** project-level settings (`.zed/settings.json`).
    - Support for **Antigravity** project-level settings (`.agents/`).
    - Detection for **Shared Instructions** via `AGENTS.md` files.
- **Enhanced MCP Inventory**:
    - Enumerate MCP servers configured in Zed (`context_servers`).
    - Enumerate MCP servers in Antigravity/Gemini settings.

## [1.1.0] - 2026-04-18

### Added
- **Advanced analytics widgets**: Migrated "Events by Agent", "Block Rate Over Time", and "Inspection Method Distribution" from the workbench.
- **Improved Monitoring**: Added Top 10 Blocked Inputs leaderboard and detailed Latency Distribution (P50/P95/P99) for better performance visibility.
- **Session Intelligence**: Comprehensive Session Summary table with branch and commit metadata.
- **Hook Coverage Matrix**: Real-time visibility of protected tool surfaces in the sidebar.
- **Premium UX Styling**: Ported the Tokyo Night-inspired theme (Streamlit sub-component) from LLM Security Workbench.
- **Improved Information Hierarchy**: Reordered dashboard tabs to make "System Blueprint" (architecture & guide) the default entry page.
- **Premium Nomenclature**: Updated tab names:
    - **🔍 Forensics & Logs** — filterable history of all security events
    - **📊 Dashboard** — advanced analytics including block rate trends and latency stats
    - **🛡️ AI Posture & Discovery** — posture scan: installed agents, hook coverage map, and trust findings
- **Visual Consistency**: Synchronized `BLOCK_AUDITED` verdict highlights to "Mango Yellow" across all analytics views.

### Changed
- **Dashboard Layout**: Optimized UI from 2-column to 3-column layout for higher information density.
- **Visual Branding**: Integrated custom `.streamlit/config.toml` for cross-platform theme consistency.

## [1.0.0] - 2026-04-16

### Added
- **Advanced Dashboard Filtering**: Sidebar filters for Agent, Session, Tool, and Verdict in the Audit Explorer.
- **Security Dashboard UI**: Standalone Streamlit interface for Live Feed, Audit Explorer, and security metrics.
- **Repository Carve-Out**: Initial standalone release extracted from `llm-sec-workbench`.
- **Modular Core**: Refactored logic into `coding_agent_guard/core` (config, redactor, allowlist, classifier, telemetry).
- **Agent Adapters**: Unified adapter interface for Claude Code and Gemini CLI (`coding_agent_guard/adapters`).
- **Decoupled Rules**: Security policies now stored in YAML files (`coding_agent_guard/rules`) for easier updates.
- **Standalone CLI**: `main.py` entry point for hook integration.
- **PRD & Roadmap**: New Product Requirements Document and development roadmap.
- **Improved Telemetry**: Enhanced Git metadata collection and session tracking in audit logs.
- **Protected Paths**: Added hard-blocking for modifications to the guard's own configuration files.

### Changed
- **Config Management**: Migrated from a single workbench `config.yaml` to dedicated `config.yaml` and `patterns.yaml` within the package.
- **Architecture**: Moved from a monolithic hook script to a package-based structure for better maintainability.
- **Dependencies**: Reduced requirements to the bare essentials (`ollama`, `pyyaml`, `python-dotenv`).

### Removed
- **Workbench UI**: Stripped out Streamlit and web framework dependencies to focus on CLI/Hook performance.
- **Security Research Tools**: Removed red-teaming and batch fuzzing logic as they are not core to the standalone guard's mission.
- **AIRS Cloud Integration**: Removed cloud-based gates to ensure the guard remains 100% local and privacy-preserving.

---
[1.0.0]: https://github.com/your-repo/Coding-Agent-Guard/releases/tag/v1.0.0
