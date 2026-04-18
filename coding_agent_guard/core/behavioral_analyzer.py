"""Behavioral Analyzer: compares AI agent intent (artifacts) with actions (tool calls).
Flags discrepancies or 'shadow actions' that weren't mentioned in the plan.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict

class BehavioralAnalyzer:
    """Analyzes audit logs to detect drift between agent plans and actual behavior."""
    
    def __init__(self, audit_path: Path):
        self.audit_path = audit_path

    def analyze_session(self, session_id: str) -> List[Dict]:
        """Cross-reference intent and action events for a session."""
        events = self._load_session_events(session_id)
        
        intents = [e for e in events if e.get("event_type") == "ARTIFACT_UPDATE"]
        actions = [e for e in events if e.get("event_type") in ("TOOL_CALL", "SHELL_COMMAND", "MCP_TOOL_CALL")]
        
        findings = []
        
        # Simple heuristic: if there are many actions but no intent/plan update recently, flag it.
        if actions and not intents:
            findings.append({
                "category": "NO_PLAN_DETECTED",
                "severity": "MEDIUM",
                "detail": "Agent is executing tools without an established implementation plan or task list."
            })
            
        # Check for 'Danger' keywords in actions that aren't in intents
        danger_keywords = ["rm", "delete", "curl", "wget", "ssh", "chmod"]
        for action in actions:
            cmd = str(action.get("data", {}).get("command", "") or action.get("tool_input", ""))
            matched = [k for k in danger_keywords if k in cmd.lower()]
            if matched:
                # See if this keyword appears in any preceding intent
                action_ts = action.get("timestamp")
                preceding_intent = [i for i in intents if i.get("timestamp") < action_ts]
                
                intent_text = " ".join([str(i.get("data", {}).get("intent_preview", "")) for i in preceding_intent]).lower()
                
                for k in matched:
                    if k not in intent_text:
                        findings.append({
                            "category": "UNPLANNED_DANGEROUS_ACTION",
                            "severity": "HIGH",
                            "detail": f"Unplanned sensitive action detected: '{k}' used in command but not mentioned in preceding agent plans.",
                            "action_preview": cmd[:100]
                        })
                        
        return findings

    def _load_session_events(self, session_id: str) -> List[Dict]:
        events = []
        fpath = self.audit_path / f"{session_id}.jsonl"
        if fpath.exists():
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        continue
        return events
