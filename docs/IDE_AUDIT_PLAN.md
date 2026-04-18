# IDE & Antigravity Audit Expansion Plan

This plan outlines a staged approach to enhancing auditing capabilities for **Antigravity** and **VS Code** AI agents within `Coding-Agent-Guard`.

## Overview

The goal is to extend the existing "Action Guard" and "Injection Guard" primitives to agents that do not natively supporthooks (like Claude/Gemini). This will be achieved by moving from direct interception to **Artifact-Based** and **Environment-Based** auditing.

## Enforcement Mode

> [!IMPORTANT]
> All proposed changes will operate in **AUDIT mode only** (non-blocking) by default. This ensures complete observability without disrupting agent workflows.

---

## Priority Stages

### Stage 1: Artifact & Discovery Enhancement (Priority: HIGH)
**Goal:** Leverage existing Antigravity artifacts and VS Code configurations for deeper behavioral insights.

- **Artifact Watching:** Automatically detect and digest Antigravity artifact files (`implementation_plan.md`, `walkthrough.md`, `task.md`).
- **Intent Logging:** Emit audit events when the agent updates its plan or status, capturing the *stated intent* of the agent.
- **Shadow Scan++:** Enhance the `shadow-ai` discovery logic to find orphaned or hidden agent worktrees.

### Stage 2: Passive MCP Auditing (Priority: MEDIUM)
**Goal:** Intercept and log tool calls made through the Model Context Protocol (MCP) in VS Code.

- **MCP Shim:** Create a lightweight JSON-RPC proxy that can be wrapped around any local MCP server command.
- **Protocol Interception:** Parse `tools/call` requests/responses and log the full payload to the Guard audit file without interrupting the session.

### Stage 3: Universal Shell Observation (Priority: MEDIUM)
**Goal:** Capture shell commands from any agent (Antigravity `run_command`, VS Code terminals) regardless of native hook support.

- **Shell Wrapper:** A "Audit-only" shell wrapper that logs all executed commands before passing them to the system shell.
- **Environment Injection:** Configure the `SHELL` or `PATH` environment variable for agent processes to use the Guard wrapper.

### Stage 4: Behavioral Cross-Referencing (Priority: LOW)
**Goal:** Detect "Drift" or "Shadow Actions" by comparing stated intent with actual tool usage.

- **Intent vs Action:** Join "Intent" logs (artifacts) with "Action" logs (shell/tool calls).
- **Drift Detection:** Flag discrepancies where the agent's actions do not align with its approved implementation plan.

---

## Roadmap

- [ ] **Phase 1:** Implement Antigravity artifact watcher.
- [ ] **Phase 2:** Design the universal MCP shim.
- [ ] **Phase 3:** Develop the audit-only shell wrapper.
- [ ] **Phase 4:** Integrate cross-reference logic into the Dashboard.
