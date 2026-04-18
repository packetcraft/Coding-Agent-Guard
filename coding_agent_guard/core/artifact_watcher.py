"""Service to watch Antigravity artifact files and log updates to the audit trail."""
from __future__ import annotations

import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List

from coding_agent_guard.core.config import Config
from coding_agent_guard.core.telemetry import write_audit, utcnow

class ArtifactWatcher:
    """Monitors Antigravity artifacts (plans, tasks, walkthroughs) for changes."""
    
    def __init__(self, audit_path: Path):
        self.audit_path = audit_path
        self.hashes: Dict[str, str] = {}  # filepath -> content_hash
        
    def _calculate_hash(self, path: Path) -> str:
        try:
            content = path.read_text(encoding="utf-8")
            return hashlib.sha256(content.encode("utf-8")).hexdigest()
        except Exception:
            return ""

    def watch_repo(self, repo_path: str, artifact_files: List[str], session_id: str):
        """Perform a single-pass check on artifact files in a repo."""
        repo = Path(repo_path)
        for filename in artifact_files:
            file_path = repo / filename
            if not file_path.exists():
                continue
                
            current_hash = self._calculate_hash(file_path)
            old_hash = self.hashes.get(str(file_path))
            
            if current_hash != old_hash:
                # Content changed (or first time seeing it)
                self.hashes[str(file_path)] = current_hash
                
                # Emit an audit event for the artifact update
                cfg = Config()
                record = {
                    "schema_version": "v1",
                    "event_type": "ARTIFACT_UPDATE",
                    "timestamp": utcnow(),
                    "session_id": session_id,
                    "agent": "Antigravity-Watcher",
                    "data": {
                        "repo_path": repo_path,
                        "file_name": filename,
                        "file_path": str(file_path),
                        "intent_preview": self._get_preview(file_path),
                    }
                }
                write_audit(
                    audit_path=self.audit_path,
                    session_id=session_id,
                    record=record,
                    is_new_session=False,
                    hook_model=cfg.guard_model,
                    timeout_ms=cfg.timeout_ms,
                    agent_name="Antigravity-Watcher"
                )

    def _get_preview(self, path: Path) -> str:
        """Return the first few lines of the file as a preview of the agent's intent."""
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            # Find first non-empty lines that aren't headers if possible
            relevant = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
            return " ".join(relevant[:3])[:200]
        except Exception:
            return ""
