"""Shadow AI discovery — data models."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentInfo:
    name: str
    version: str | None
    install_path: str
    install_method: str  # "npm", "pip", "path", "vscode_extension", "app"
    auth_type: str | None = None


@dataclass
class HookEntry:
    event: str
    matcher: str
    command: str
    is_guard: bool


@dataclass
class RepoConfig:
    repo_path: str
    agent: str
    config_path: str
    hook_entries: list[HookEntry] = field(default_factory=list)
    mcp_server_count: int = 0
    inherited_from: str | None = None
    artifact_files: list[str] = field(default_factory=list)
    external_brain_session: str | None = None


@dataclass
class GapResult:
    repo_path: str
    agent: str
    status: str  # "COVERED", "SHADOW_HOOK", "ARTIFACT_ONLY", "EXTERNAL_BRAIN", "UNGUARDED"
    hook_command: str | None
    inherited: bool
    config_path: str | None
    artifact_files: list[str] = field(default_factory=list)
    external_brain_session: str | None = None



@dataclass
class McpServer:
    name: str
    transport: str        # "local" | "remote"
    command: str | None   # set for local
    url: str | None       # set for remote
    trust: bool
    agent: str            # which agent owns this config
    source: str           # config file path
    tool_count: int | None = None  # filled by Phase 4 enumeration


@dataclass
class Finding:
    id: str
    category: str   # e.g. "REMOTE_MCP_TRUST_TRUE", "OVERLY_BROAD_FOLDER_TRUST"
    severity: str   # "HIGH" | "MEDIUM" | "LOW"
    agent: str | None
    source: str
    detail: str
    remediation: str


@dataclass
class ScanResult:
    scan_id: str
    timestamp: str
    scan_root: str
    agents_found: list[AgentInfo] = field(default_factory=list)
    repo_configs: list[RepoConfig] = field(default_factory=list)
    gap_results: list[GapResult] = field(default_factory=list)
    mcp_servers: list[McpServer] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
