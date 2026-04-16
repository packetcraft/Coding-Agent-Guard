"""Orchestrator: run all Phase 1 probes, emit DISCOVERY_SCAN audit entry, expose CLI."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from coding_agent_guard.discovery import ScanResult
from coding_agent_guard.discovery.agents import detect_agents
from coding_agent_guard.discovery.config_crawler import crawl
from coding_agent_guard.discovery.gap_analyzer import analyze
from coding_agent_guard.discovery.mcp_inventory import inventory as mcp_inventory
from coding_agent_guard.discovery.trust_analyzer import analyze as trust_analyze
from coding_agent_guard.discovery.report import as_text, as_json
from coding_agent_guard.core.telemetry import utcnow


_DEFAULT_AUDIT_FILE = "shadow_ai_scans.jsonl"


def _default_scan_root() -> str:
    """Default to the parent of the user's home Documents/github dir if it exists,
    otherwise fall back to the home directory."""
    import os
    if sys.platform == "win32":
        base = Path(os.environ.get("USERPROFILE", Path.home()))
    else:
        base = Path.home()
    for candidate in [
        base / "Documents" / "github",
        base / "Documents" / "GitHub",
        base / "projects",
        base / "code",
        base / "src",
    ]:
        if candidate.is_dir():
            return str(candidate)
    return str(base)


def run_scan(scan_root: str | None = None) -> ScanResult:
    """Execute all Phase 1 probes and return a ScanResult."""
    root = scan_root or _default_scan_root()
    scan_id = str(uuid.uuid4())[:8]
    timestamp = utcnow()

    agents = detect_agents()
    repo_configs = crawl(root)
    gap_results = analyze(repo_configs)
    mcp_servers = mcp_inventory(root)
    findings = trust_analyze(root, mcp_servers, gap_results)

    return ScanResult(
        scan_id=scan_id,
        timestamp=timestamp,
        scan_root=root,
        agents_found=agents,
        repo_configs=repo_configs,
        gap_results=gap_results,
        mcp_servers=mcp_servers,
        findings=findings,
    )


def emit_audit(result: ScanResult, audit_dir: Path) -> None:
    """Append DISCOVERY_SCAN JSON record to the shadow_ai_scans.jsonl audit file."""
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / _DEFAULT_AUDIT_FILE
    record = json.loads(as_json(result))
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def cli() -> None:
    """Entry point for `coding-agent-guard shadow-ai`."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="coding-agent-guard shadow-ai",
        description="Discover AI coding agents, hook coverage, and security posture on this machine.",
    )
    parser.add_argument(
        "--root",
        default=None,
        metavar="DIR",
        help="Root directory to scan for repos (default: auto-detected)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--no-audit",
        action="store_true",
        help="Do not write results to the audit log",
    )

    args = parser.parse_args()

    result = run_scan(scan_root=args.root)

    if args.output == "json":
        print(as_json(result))
    else:
        print(as_text(result))

    if not args.no_audit:
        # Resolve audit dir relative to cwd (same as the main guard)
        from coding_agent_guard.core.config import Config
        cfg = Config()
        audit_dir = (Path.cwd() / cfg.audit_path).resolve()
        emit_audit(result, audit_dir)
        if args.output == "text":
            print(f"\n  Audit record written to: {audit_dir / _DEFAULT_AUDIT_FILE}")


if __name__ == "__main__":
    cli()
