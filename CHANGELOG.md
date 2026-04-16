# Changelog

All notable changes to the **Coding Agent Guard** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
