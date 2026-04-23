from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from coding_agent_guard.core.config import Config
from coding_agent_guard.core.telemetry import utcnow
from coding_agent_guard.discovery.scanner import run_scan, diff_scans, load_all_scans, emit_audit
from coding_agent_guard.discovery.report import as_json


class PatrolEngine:
    """
    Automated security posture patrol.
    Runs discovery scans on a schedule and detects 'Posture Drift'.
    """

    def __init__(self, audit_dir: Path | None = None):
        cfg = Config()
        self.audit_dir = audit_dir or (Path.cwd() / cfg.audit_path).resolve()
        self.patrol_file = self.audit_dir / "patrol_history.jsonl"

    def run_patrol(self, scan_root: str | None = None) -> dict[str, Any]:
        """
        Run a discovery scan, compare it to the last one, and log the results.
        Returns the drift results.
        """
        # 1. Load previous scan for comparison
        all_scans = load_all_scans(self.audit_dir)
        previous_scan = all_scans[-1] if all_scans else None

        # 2. Run new scan
        result = run_scan(scan_root=scan_root)
        emit_audit(result, self.audit_dir)
        current_scan = json.loads(as_json(result))

        # 3. Diff scans
        drift = {}
        if previous_scan:
            drift = diff_scans(current_scan, previous_scan)
        else:
            drift = {
                "status": "INITIAL_SCAN",
                "message": "First patrol run complete. No baseline for comparison.",
                "posture_score": current_scan.get("summary", {}).get("posture_maturity_score", 0)
            }

        # 4. Log patrol event
        patrol_event = {
            "event_type": "PATROL_RUN",
            "timestamp": utcnow(),
            "scan_id": current_scan.get("scan_id"),
            "drift": drift,
            "summary": current_scan.get("summary", {})
        }

        self.audit_dir.mkdir(parents=True, exist_ok=True)
        with open(self.patrol_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(patrol_event) + "\n")

        return drift

    def start_background_loop(self, interval_seconds: int = 86400):
        """
        Start a simple persistent loop for the patrol.
        Default is 24 hours.
        """
        print(f"[*] Starting Security Patrol background loop (interval: {interval_seconds}s)")
        try:
            while True:
                print(f"[*] Running scheduled patrol at {utcnow()}")
                try:
                    drift = self.run_patrol()
                    if drift.get("newly_unprotected"):
                        print(f"[!] ALERT: {len(drift['newly_unprotected'])} repos lost protection!")
                except Exception as e:
                    print(f"[!] Patrol failed: {e}")
                
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("[*] Security Patrol stopped.")


def cli():
    """Entry point for `coding-agent-guard patrol`."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="coding-agent-guard patrol",
        description="Automated security posture checks for AI agents.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Patrol commands")

    # Run command
    subparsers.add_parser("run", help="Run a security patrol check now")

    # Status command
    subparsers.add_parser("status", help="Show last patrol results and drift")

    # Background command
    bg_parser = subparsers.add_parser("serve", help="Start the persistent background patrol service")
    bg_parser.add_argument("--interval", type=int, default=86400, help="Interval in seconds (default: 86400 / 24h)")

    args = parser.parse_args()
    engine = PatrolEngine()

    if args.command == "run":
        print("[*] Running manual security patrol...")
        drift = engine.run_patrol()
        print("[+] Patrol complete.")
        if drift.get("posture_score_delta") is not None:
            delta = drift["posture_score_delta"]
            sign = "+" if delta >= 0 else ""
            print(f"[*] Posture Score Delta: {sign}{delta}%")
        
        if drift.get("newly_unprotected"):
            print("[!] WARNING: Newly unprotected repositories found!")
            for r in drift["newly_unprotected"]:
                print(f"    - {r['repo_path']} ({r['agent']})")

    elif args.command == "status":
        history_file = engine.patrol_file
        if not history_file.exists():
            print("[!] No patrol history found. Run 'guard patrol run' first.")
            return

        with open(history_file, encoding="utf-8") as f:
            lines = f.readlines()
            if not lines:
                print("[!] Patrol history is empty.")
                return
            
            last_patrol = json.loads(lines[-1])
            print(f"[*] Last Patrol Run: {last_patrol.get('timestamp')}")
            print(f"[*] Scan ID        : {last_patrol.get('scan_id')}")
            drift = last_patrol.get("drift", {})
            if drift.get("posture_score_delta") is not None:
                delta = drift["posture_score_delta"]
                sign = "+" if delta >= 0 else ""
                print(f"[*] Posture Drift  : {sign}{delta}%")
            
            summary = last_patrol.get("summary", {})
            print(f"[*] Maturity Score : {summary.get('posture_maturity_score', 0)}%")

    elif args.command == "serve":
        engine.start_background_loop(interval_seconds=args.interval)

    else:
        parser.print_help()
