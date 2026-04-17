from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

def get_git_info() -> tuple[str | None, str | None]:
    def _run(cmd: list[str]) -> str | None:
        try:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            return None
    return (
        _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        _run(["git", "rev-parse", "--short", "HEAD"]),
    )

def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

def write_audit(
    audit_path: Path,
    session_id: str,
    record: dict,
    is_new_session: bool,
    hook_model: str,
    timeout_ms: int,
    agent_name: str,
) -> None:
    audit_path.mkdir(parents=True, exist_ok=True)
    fpath = audit_path / f"{session_id}.jsonl"

    with open(fpath, "a", encoding="utf-8") as f:
        if is_new_session:
            branch, commit = get_git_info()
            session_start = {
                "schema_version": "v1",
                "event_type":     "SESSION_START",
                "timestamp":      utcnow(),
                "session_id":     session_id,
                "agent":          agent_name,
                "cwd":            str(Path.cwd()),
                "git_branch":     branch,
                "git_commit":     commit,
                "hook_model":     hook_model,
                "hook_timeout_ms": timeout_ms,
            }
            f.write(json.dumps(session_start) + "\n")
        f.write(json.dumps(record) + "\n")
