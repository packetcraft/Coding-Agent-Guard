"""Orchestrator: run all Phase 1 probes, emit DISCOVERY_SCAN audit entry, expose CLI."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from coding_agent_guard.discovery import ScanResult
from coding_agent_guard.discovery.agents import detect_agents, detect_cicd_agents
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

    agents = detect_agents() + detect_cicd_agents(root)
    repo_configs = crawl(root)
    gap_results = analyze(repo_configs)
    mcp_servers = mcp_inventory(root)
    findings = trust_analyze(root, agents, mcp_servers, gap_results)

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


def diff_scans(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    """Compare two scan dicts and return a structured diff."""
    def _agent_names(scan: dict) -> set[str]:
        return {a["name"] for a in scan.get("agents", [])}

    def _pair_statuses(scan: dict) -> dict[tuple[str, str], str]:
        return {
            (r["repo_path"], r["agent"]): r["status"]
            for r in scan.get("coverage_map", [])
        }

    def _mcp_names(scan: dict) -> set[str]:
        return {(s["name"], s["source"]) for s in scan.get("mcp_servers", [])}

    cur_agents = _agent_names(current)
    prev_agents = _agent_names(previous)
    cur_pairs = _pair_statuses(current)
    prev_pairs = _pair_statuses(previous)
    cur_mcps = _mcp_names(current)
    prev_mcps = _mcp_names(previous)

    # Repos that degraded (were COVERED, now aren't)
    newly_unprotected = [
        {"repo_path": rp, "agent": ag, "old_status": prev_pairs[k], "new_status": cur_pairs[k]}
        for k, (rp, ag) in [(k, k) for k in cur_pairs]
        if k in prev_pairs and prev_pairs[k] == "COVERED" and cur_pairs[k] != "COVERED"
    ]

    # Repos that improved (were UNGUARDED, now COVERED)
    newly_protected = [
        {"repo_path": rp, "agent": ag, "old_status": prev_pairs[k], "new_status": cur_pairs[k]}
        for k, (rp, ag) in [(k, k) for k in cur_pairs]
        if k in prev_pairs and prev_pairs[k] != "COVERED" and cur_pairs[k] == "COVERED"
    ]

    score_current = current.get("summary", {}).get("posture_maturity_score", 0)
    score_previous = previous.get("summary", {}).get("posture_maturity_score", 0)

    return {
        "from_scan_id": previous.get("scan_id"),
        "to_scan_id": current.get("scan_id"),
        "from_timestamp": previous.get("timestamp"),
        "to_timestamp": current.get("timestamp"),
        "posture_score_delta": round(score_current - score_previous, 1),
        "new_agents": sorted(cur_agents - prev_agents),
        "removed_agents": sorted(prev_agents - cur_agents),
        "newly_unprotected": newly_unprotected,
        "newly_protected": newly_protected,
        "new_mcp_servers": [{"name": n, "source": s} for n, s in sorted(cur_mcps - prev_mcps)],
        "removed_mcp_servers": [{"name": n, "source": s} for n, s in sorted(prev_mcps - cur_mcps)],
    }


def load_all_scans(audit_dir: Path) -> list[dict[str, Any]]:
    """Load all DISCOVERY_SCAN records from the audit file, oldest first."""
    audit_file = audit_dir / _DEFAULT_AUDIT_FILE
    scans: list[dict] = []
    if not audit_file.exists():
        return scans
    try:
        with open(audit_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("event_type") == "DISCOVERY_SCAN":
                        scans.append(rec)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return scans


def _apply_fix(gap_results: list, scan_root: str) -> None:
    """Interactively write guard hooks for unguarded Claude repos."""
    import shutil
    unguarded_claude = [
        g for g in gap_results
        if g.status in ("UNGUARDED", "BROKEN_HOOK") and g.agent == "Claude"
    ]
    if not unguarded_claude:
        print("  No unguarded Claude repos found — nothing to fix.")
        return

    guard_bin = shutil.which("coding-agent-guard") or "coding-agent-guard"
    hook_block = {
        "hooks": {
            "PreToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": f"{guard_bin} pre-tool-use"}]}],
            "PostToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": f"{guard_bin} post-tool-use"}]}],
        }
    }

    print(f"\n  Found {len(unguarded_claude)} unguarded Claude repo(s).\n")
    for g in unguarded_claude:
        settings_path = Path(g.repo_path) / ".claude" / "settings.json"
        print(f"  Repo   : {g.repo_path}")
        print(f"  Status : {g.status}")
        print(f"  Target : {settings_path}")
        print(f"  Will write hooks block:\n")
        print("    " + json.dumps(hook_block, indent=2).replace("\n", "\n    "))
        print()

        answer = input("  Apply fix? [y/N] ").strip().lower()
        if answer != "y":
            print("  Skipped.\n")
            continue

        try:
            existing: dict = {}
            if settings_path.exists():
                try:
                    existing = json.loads(settings_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            # Merge hooks (don't overwrite unrelated settings)
            existing_hooks = existing.get("hooks", {})
            for event, entries in hook_block["hooks"].items():
                if event not in existing_hooks:
                    existing_hooks[event] = entries
                else:
                    # Prepend guard hook if not already present
                    guard_cmd = entries[0]["hooks"][0]["command"]
                    if not any(
                        h.get("command", "") == guard_cmd
                        for item in existing_hooks[event]
                        for h in item.get("hooks", [])
                    ):
                        existing_hooks[event] = entries + existing_hooks[event]
            existing["hooks"] = existing_hooks
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            print(f"  Written: {settings_path}\n")
        except Exception as exc:
            print(f"  Error writing {settings_path}: {exc}\n")


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
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Compare latest scan against previous scan and show drift",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Interactively write guard hooks for unguarded Claude repos",
    )

    args = parser.parse_args()

    from coding_agent_guard.core.config import Config
    cfg = Config()
    audit_dir = (Path.cwd() / cfg.audit_path).resolve()

    result = run_scan(scan_root=args.root)

    if args.output == "json":
        print(as_json(result))
    else:
        print(as_text(result))

    if not args.no_audit:
        emit_audit(result, audit_dir)
        if args.output == "text":
            print(f"\n  Audit record written to: {audit_dir / _DEFAULT_AUDIT_FILE}")

    if args.diff:
        all_scans = load_all_scans(audit_dir)
        if len(all_scans) < 2:
            print("\n  --diff: Not enough scan history (need at least 2 scans). Run again later.")
        else:
            current_dict = json.loads(as_json(result))
            previous_dict = all_scans[-2] if len(all_scans) >= 2 else all_scans[-1]
            drift = diff_scans(current_dict, previous_dict)
            print("\n" + "=" * 70)
            print("  POSTURE DRIFT (vs previous scan)")
            print("=" * 70)
            print(f"  From scan : {drift['from_scan_id']} @ {drift.get('from_timestamp', '?')}")
            print(f"  To scan   : {drift['to_scan_id']} @ {drift.get('to_timestamp', '?')}")
            delta = drift["posture_score_delta"]
            sign = "+" if delta >= 0 else ""
            print(f"  Score delta: {sign}{delta:.1f}%")
            if drift["new_agents"]:
                print(f"  New agents detected    : {', '.join(drift['new_agents'])}")
            if drift["removed_agents"]:
                print(f"  Agents no longer found : {', '.join(drift['removed_agents'])}")
            if drift["newly_unprotected"]:
                print("  [!] Repos that LOST protection:")
                for r in drift["newly_unprotected"]:
                    print(f"      {r['repo_path']} ({r['agent']}): {r['old_status']} → {r['new_status']}")
            if drift["newly_protected"]:
                print("  [OK] Repos that GAINED protection:")
                for r in drift["newly_protected"]:
                    print(f"      {r['repo_path']} ({r['agent']}): {r['old_status']} → {r['new_status']}")
            if drift["new_mcp_servers"]:
                print(f"  New MCP servers : {[s['name'] for s in drift['new_mcp_servers']]}")
            if not any([drift["new_agents"], drift["removed_agents"], drift["newly_unprotected"],
                        drift["newly_protected"], drift["new_mcp_servers"], drift["removed_mcp_servers"]]):
                print("  No changes detected since previous scan.")
            print("=" * 70)

    if args.fix:
        print("\n" + "=" * 70)
        print("  REMEDIATION — Auto-fix unguarded Claude repos")
        print("=" * 70)
        _apply_fix(result.gap_results, result.scan_root)


if __name__ == "__main__":
    cli()
