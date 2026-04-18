"""Format scan results as human-readable text or structured JSON."""
from __future__ import annotations

import json

from coding_agent_guard.discovery import ScanResult


_STATUS_ORDER = {"UNGUARDED": 0, "SHADOW_HOOK": 1, "COVERED": 2}
_SEV_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _status_icon(status: str) -> str:
    return {"COVERED": "[OK]", "SHADOW_HOOK": "[!]", "UNGUARDED": "[X]"}.get(status, status)


def _sev_icon(severity: str) -> str:
    return {"HIGH": "[HIGH]", "MEDIUM": "[MED] ", "LOW": "[LOW] "}.get(severity, severity)


def as_text(result: ScanResult) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("  Shadow AI Discovery Scan")
    lines.append(f"  Scan root : {result.scan_root}")
    lines.append(f"  Timestamp : {result.timestamp}")
    lines.append(f"  Scan ID   : {result.scan_id}")
    lines.append("=" * 70)

    # ── Detected agents ───────────────────────────────────────────────────────
    lines.append("")
    lines.append("DETECTED AGENTS")
    lines.append("-" * 70)
    if result.agents_found:
        for a in result.agents_found:
            ver = a.version or "version unknown"
            auth = f"  auth: {a.auth_type}" if a.auth_type else ""
            lines.append(f"  {a.name:<28} {ver:<20} [{a.install_method}]{auth}")
    else:
        lines.append("  No AI coding agents detected.")

    # ── Coverage map ──────────────────────────────────────────────────────────
    lines.append("")
    lines.append("COVERAGE MAP  (sorted: unguarded first)")
    lines.append("-" * 70)
    sorted_gaps = sorted(
        result.gap_results,
        key=lambda g: (_STATUS_ORDER.get(g.status, 9), g.agent, g.repo_path),
    )
    if sorted_gaps:
        lines.append(f"  {'Status':<14} {'Agent':<12} {'Inherited':<10} Repo")
        lines.append(f"  {'-'*12}   {'-'*10}   {'-'*8}   {'-'*40}")
        for g in sorted_gaps:
            icon = _status_icon(g.status)
            inh = "yes" if g.inherited else "no"
            repo = g.repo_path
            if len(repo) > 50:
                repo = "..." + repo[-47:]
            lines.append(f"  {icon:<6} {g.status:<10} {g.agent:<12} {inh:<10} {repo}")
    else:
        lines.append("  No repo/agent pairs found in scan root.")

    # ── MCP Surface ───────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"MCP SURFACE  ({len(result.mcp_servers)} server(s))")
    lines.append("-" * 70)
    if result.mcp_servers:
        lines.append(f"  {'Name':<30} {'Agent':<22} {'Transport':<8} {'Trust':<6} Source")
        lines.append(f"  {'-'*28}   {'-'*20}   {'-'*6}   {'-'*4}   {'-'*30}")
        for s in result.mcp_servers:
            trust_flag = "YES" if s.trust else "no"
            src = s.source
            if len(src) > 35:
                src = "..." + src[-32:]
            lines.append(
                f"  {s.name:<30} {s.agent:<22} {s.transport:<8} {trust_flag:<6} {src}"
            )
    else:
        lines.append("  No MCP servers configured.")

    # ── Findings ──────────────────────────────────────────────────────────────
    sorted_findings = sorted(result.findings, key=lambda f: _SEV_ORDER.get(f.severity, 9))
    lines.append("")
    lines.append(f"FINDINGS  ({len(result.findings)} total)")
    lines.append("-" * 70)
    if sorted_findings:
        for f in sorted_findings:
            lines.append(f"  {_sev_icon(f.severity)} {f.id}  {f.category}")
            if f.agent:
                lines.append(f"         Agent  : {f.agent}")
            lines.append(f"         Source : {f.source}")
            lines.append(f"         Detail : {f.detail}")
            lines.append(f"         Fix    : {f.remediation}")
            lines.append("")
    else:
        lines.append("  No findings.")

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(result.gap_results)
    covered = sum(1 for g in result.gap_results if g.status == "COVERED")
    shadow = sum(1 for g in result.gap_results if g.status == "SHADOW_HOOK")
    unguarded = sum(1 for g in result.gap_results if g.status == "UNGUARDED")
    high_findings = sum(1 for f in result.findings if f.severity == "HIGH")
    med_findings = sum(1 for f in result.findings if f.severity == "MEDIUM")

    lines.append("SUMMARY")
    lines.append("-" * 70)
    lines.append(f"  Agents detected     : {len(result.agents_found)}")
    lines.append(f"  Repo/agent pairs    : {total}")
    lines.append(f"  Covered             : {covered}")
    lines.append(f"  Shadow hooks        : {shadow}")
    lines.append(f"  Unguarded           : {unguarded}")
    lines.append(f"  MCP servers         : {len(result.mcp_servers)}")
    lines.append(f"  Remote MCPs (trust) : {sum(1 for s in result.mcp_servers if s.transport == 'remote' and s.trust)}")
    lines.append(f"  High findings       : {high_findings}")
    lines.append(f"  Medium findings     : {med_findings}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def as_markdown(result: ScanResult) -> str:
    lines: list[str] = []
    lines.append(f"# Shadow AI Discovery Report — {result.scan_id}")
    lines.append(f"**Scan Root:** `{result.scan_root}`  ")
    lines.append(f"**Timestamp:** {result.timestamp}  ")
    lines.append("")

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(result.gap_results)
    covered = sum(1 for g in result.gap_results if g.status == "COVERED")
    unguarded = sum(1 for g in result.gap_results if g.status == "UNGUARDED")
    ides_count = sum(1 for a in result.agents_found if any(x in a.name.lower() for x in ["vscode", "vs code", "zed", "antigravity", "cursor", "windsurf"]))
    agents_count = len(result.agents_found) - ides_count

    lines.append("## Executive Summary")
    lines.append(f"- **IDEs Detected:** {ides_count}")
    lines.append(f"- **CLI Agents Detected:** {agents_count}")
    lines.append(f"- **Repo/Agent Pairs:** {total}")
    lines.append(f"- **Covered:** {covered} ({(covered/total*100 if total else 0):.1f}%)")
    lines.append(f"- **Unguarded:** {unguarded}")
    lines.append(f"- **High Severity Findings:** {sum(1 for f in result.findings if f.severity == 'HIGH')}")
    lines.append("")

    # ── Findings ──────────────────────────────────────────────────────────────
    lines.append("## Security Findings")
    if result.findings:
        sorted_findings = sorted(result.findings, key=lambda f: _SEV_ORDER.get(f.severity, 9))
        for f in sorted_findings:
            lines.append(f"### {f.severity}: {f.category} ({f.id})")
            if f.agent:
                lines.append(f"- **Agent:** {f.agent}")
            lines.append(f"- **Source:** `{f.source}`")
            lines.append(f"- **Detail:** {f.detail}")
            lines.append(f"- **Remediation:** {f.remediation}")
            lines.append("")
    else:
        lines.append("No security findings detected.")
    lines.append("")

    # ── Agent Inventory ───────────────────────────────────────────────────────
    lines.append("## Agent Inventory")
    if result.agents_found:
        lines.append("| Name | Version | Method | Auth |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for a in result.agents_found:
            lines.append(f"| {a.name} | {a.version or '—'} | {a.install_method} | {a.auth_type or '—'} |")
    else:
        lines.append("No agents detected.")
    lines.append("")

    # ── Coverage Map ──────────────────────────────────────────────────────────
    lines.append("## Hook Coverage Map")
    if result.gap_results:
        lines.append("| Status | Agent | Inherited | Repo Path |")
        lines.append("| :--- | :--- | :--- | :--- |")
        sorted_gaps = sorted(
            result.gap_results,
            key=lambda g: (_STATUS_ORDER.get(g.status, 9), g.agent, g.repo_path),
        )
        for g in sorted_gaps:
            inh = "yes" if g.inherited else "no"
            lines.append(f"| {g.status} | {g.agent} | {inh} | `{g.repo_path}` |")
    else:
        lines.append("No repo/agent pairs found.")
    lines.append("")

    # ── MCP Surface ───────────────────────────────────────────────────────────
    lines.append("## MCP Surface")
    if result.mcp_servers:
        lines.append("| Name | Agent | Transport | Trust | Source |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for s in result.mcp_servers:
            trust = "YES" if s.trust else "no"
            lines.append(f"| {s.name} | {s.agent} | {s.transport} | {trust} | `{s.source}` |")
    else:
        lines.append("No MCP servers configured.")
    lines.append("")

    return "\n".join(lines)


def as_json(result: ScanResult) -> str:
    ides_count = sum(1 for a in result.agents_found if any(x in a.name.lower() for x in ["vscode", "vs code", "zed", "antigravity", "cursor", "windsurf"]))
    agents_count = len(result.agents_found) - ides_count

    data = {
        "schema_version": "v1",
        "event_type": "DISCOVERY_SCAN",
        "scan_id": result.scan_id,
        "timestamp": result.timestamp,
        "scan_root": result.scan_root,
        "summary": {
            "ides_found": ides_count,
            "agents_found": agents_count,
            "repo_agent_pairs": len(result.gap_results),
            "covered": sum(1 for g in result.gap_results if g.status == "COVERED"),
            "shadow_hooks": sum(1 for g in result.gap_results if g.status == "SHADOW_HOOK"),
            "unguarded": sum(1 for g in result.gap_results if g.status == "UNGUARDED"),
            "mcp_servers": len(result.mcp_servers),
            "remote_mcps_trust_true": sum(
                1 for s in result.mcp_servers if s.transport == "remote" and s.trust
            ),
            "high_findings": sum(1 for f in result.findings if f.severity == "HIGH"),
            "medium_findings": sum(1 for f in result.findings if f.severity == "MEDIUM"),
            "low_findings": sum(1 for f in result.findings if f.severity == "LOW"),
        },
        "agents": [
            {
                "name": a.name,
                "version": a.version,
                "install_path": a.install_path,
                "install_method": a.install_method,
                "auth_type": a.auth_type,
            }
            for a in result.agents_found
        ],
        "coverage_map": [
            {
                "repo_path": g.repo_path,
                "agent": g.agent,
                "status": g.status,
                "hook_command": g.hook_command,
                "inherited": g.inherited,
                "config_path": g.config_path,
            }
            for g in result.gap_results
        ],
        "mcp_servers": [
            {
                "name": s.name,
                "transport": s.transport,
                "command": s.command,
                "url": s.url,
                "trust": s.trust,
                "agent": s.agent,
                "source": s.source,
                "tool_count": s.tool_count,
            }
            for s in result.mcp_servers
        ],
        "findings": [
            {
                "id": f.id,
                "category": f.category,
                "severity": f.severity,
                "agent": f.agent,
                "source": f.source,
                "detail": f.detail,
                "remediation": f.remediation,
            }
            for f in result.findings
        ],
    }
    return json.dumps(data, indent=2)
