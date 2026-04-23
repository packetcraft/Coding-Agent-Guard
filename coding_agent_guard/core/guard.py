import json
import sys
import re
from pathlib import Path

from coding_agent_guard.core.config import Config
from coding_agent_guard.core.redactor import redact, redact_dict
from coding_agent_guard.core.allowlist import is_allowlisted
from coding_agent_guard.core.classifier import classify
from coding_agent_guard.core.telemetry import write_audit, utcnow
from coding_agent_guard.core.utils import truncate_output, extract_inspectable
from coding_agent_guard.core.static_scanner import StaticScanner
from coding_agent_guard.adapters.base import detect_agent, normalize_hook_event
from coding_agent_guard.adapters.claude import ClaudeAdapter
from coding_agent_guard.adapters.gemini import GeminiAdapter

class GuardEngine:
    """Core engine for security classification and audit logging."""
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self.static_scanner = StaticScanner()

    def check_tool(
        self,
        tool_name: str,
        tool_input: dict,
        agent_name: str = "unknown",
        session_id: str = "unknown",
        cwd: str = "",
        hook_event: str = "PreToolUse",
        tool_response: str | None = None,
    ) -> tuple[str, str | None]:
        """
        Evaluate a tool call or response.
        Returns (verdict, block_reason).
        """
        hook_event = normalize_hook_event(hook_event)

        # ── Skill Attribution (MCP support) ──────────────────────────────────
        skill_id = "core"
        if "__" in tool_name:
            parts = tool_name.split("__")
            if len(parts) >= 2:
                skill_id = parts[1]

        _cwd_path = Path(cwd) if cwd else Path.cwd()
        if not _cwd_path.is_dir():
            _cwd_path = Path.cwd()
        audit_path = (_cwd_path / self.cfg.audit_path).resolve()

        # ── Detect new session (before any writes) ─────────────────────────────
        is_new_session = not (audit_path / f"{session_id}.jsonl").exists()
        if is_new_session and self.cfg.audit_only and hook_event == "PreToolUse":
            sys.stderr.buffer.write(
                "[coding-agent-guard] WARNING: audit_only=true -- guard is logging but NOT blocking.\n".encode("utf-8")
            )

        # ── PostToolUse — scan command output for exfiltration signals ─────────
        if hook_event == "PostToolUse":
            output_text = str(tool_response or "")

            # 4a. Fast-path: IPI regex blocklist
            for pattern_str in self.cfg.ipi_blocklist:
                pattern = re.compile(pattern_str)
                if pattern.search(output_text):
                    raw_output = f"BLOCK - Fast-path regex match: {pattern.pattern}"
                    redacted_output, redaction_count = redact(truncate_output(output_text))
                    record = {
                        "schema_version":    "v1",
                        "event_type":        "TOOL_CALL",
                        "timestamp":         utcnow(),
                        "session_id":        session_id,
                        "agent":             agent_name,
                        "skill_id":          skill_id,
                        "hook_event":        hook_event,
                        "tool_name":         tool_name,
                        "tool_input":        {"output_preview": redacted_output[:500]},
                        "verdict":           "BLOCK_AUDITED",
                        "inspection_method": "REGEX",
                        "block_reason":      "Prompt injection detected via fast-path regex.",
                        "guard_model":       None,
                        "guard_raw_output":  raw_output,
                        "latency_ms":        0,
                        "redactions_applied": redaction_count,
                    }
                    write_audit(audit_path, session_id, record, is_new_session, self.cfg.guard_model, self.cfg.timeout_ms, agent_name)
                    return "ALLOW", None # PostToolUse cannot block

            # 4b. Slow-path: Ollama classification (with truncation)
            truncated_output = truncate_output(output_text)
            redacted_output, redaction_count = redact(truncated_output)

            verdict, raw_output, latency_ms = classify(
                f"{tool_name}:output", redacted_output, self.cfg.guard_model, self.cfg.timeout_ms, hook_event="PostToolUse"
            )
            audited_verdict = "BLOCK_AUDITED" if verdict == "BLOCK" else verdict
            record = {
                "schema_version":    "v1",
                "event_type":        "TOOL_CALL",
                "timestamp":         utcnow(),
                "session_id":        session_id,
                "agent":             agent_name,
                "skill_id":          skill_id,
                "hook_event":        hook_event,
                "tool_name":         tool_name,
                "tool_input":        {"output_preview": redacted_output[:500]},
                "verdict":           audited_verdict,
                "inspection_method": "LLM",
                "block_reason":      "Prompt injection detected via LLM guard." if audited_verdict == "BLOCK_AUDITED" else None,
                "guard_model":       self.cfg.guard_model,
                "guard_raw_output":  raw_output,
                "latency_ms":        latency_ms,
                "redactions_applied": redaction_count,
            }
            write_audit(audit_path, session_id, record, is_new_session, self.cfg.guard_model, self.cfg.timeout_ms, agent_name)
            return "ALLOW", None

        # ── 5. PreToolUse — allowlist check (Bash only) ───────────────────────────
        if self.cfg.allowlist_enabled and tool_name.lower() in ["bash", "sh"]:
            command = tool_input.get("command", "")
            if is_allowlisted(command, self.cfg.allowlist_patterns):
                record = {
                    "schema_version":    "v1",
                    "event_type":        "TOOL_CALL",
                    "timestamp":         utcnow(),
                    "session_id":        session_id,
                    "agent":             agent_name,
                    "skill_id":          skill_id,
                    "hook_event":        hook_event,
                    "tool_name":         tool_name,
                    "tool_input":        tool_input,
                    "verdict":           "ALLOWLISTED",
                    "inspection_method": "ALLOWLIST",
                    "block_reason":      None,
                    "guard_model":       None,
                    "guard_raw_output":  None,
                    "latency_ms":        0,
                    "redactions_applied": 0,
                }
                write_audit(audit_path, session_id, record, is_new_session, self.cfg.guard_model, self.cfg.timeout_ms, agent_name)
                return "ALLOW", None

        # ── 5.5 Protected path check (Write/Edit only) ───────────────────────────
        if any(k in tool_name.lower() for k in ["write", "edit", "patch"]):
            file_path = str(tool_input.get("file_path", ""))
            norm_path = file_path.replace("\\", "/").lstrip("./")
            if any(norm_path.endswith(p) for p in self.cfg.protected_paths):
                block_reason = f"Security: modifying protected hook configuration is forbidden ({file_path})"
                record = {
                    "schema_version":    "v1",
                    "event_type":        "TOOL_CALL",
                    "timestamp":         utcnow(),
                    "session_id":        session_id,
                    "agent":             agent_name,
                    "skill_id":          skill_id,
                    "hook_event":        hook_event,
                    "tool_name":         tool_name,
                    "tool_input":        tool_input,
                    "verdict":           "BLOCK",
                    "inspection_method": "PATH",
                    "block_reason":      block_reason,
                    "guard_model":       None,
                    "guard_raw_output":  "PROTECTED_PATH_VIOLATION",
                    "latency_ms":        0,
                    "redactions_applied": 0,
                }
                write_audit(audit_path, session_id, record, is_new_session, self.cfg.guard_model, self.cfg.timeout_ms, agent_name)
                return "BLOCK", block_reason

        # ── 6. Redact secrets ─────────────────────────────────────────────────────
        inspectable_text, decoded_segments = extract_inspectable(tool_name, tool_input)
        redacted_text, _    = redact(inspectable_text)
        redacted_input, rc  = redact_dict(tool_input)

        # ── 6.5 Static Analysis (Fast-Path) ───────────────────────────────────────
        static_findings = self.static_scanner.scan_content(inspectable_text, source_name=f"tool:{tool_name}")
        if static_findings:
            high_findings = [f for f in static_findings if f.get("severity") == "HIGH"]
            if high_findings:
                finding = high_findings[0]
                block_reason = f"Security: static analysis match ({finding.get('rule_id')}): {finding.get('description')}"
                record = {
                    "schema_version":    "v1",
                    "event_type":        "TOOL_CALL",
                    "timestamp":         utcnow(),
                    "session_id":        session_id,
                    "agent":             agent_name,
                    "skill_id":          skill_id,
                    "hook_event":        hook_event,
                    "tool_name":         tool_name,
                    "tool_input":        redacted_input,
                    "decoded_segments":  decoded_segments,
                    "verdict":           "BLOCK",
                    "inspection_method": "STATIC",
                    "block_reason":      block_reason,
                    "guard_model":       None,
                    "guard_raw_output":  f"STATIC_MATCH: {finding.get('rule_id')}",
                    "latency_ms":        0,
                    "redactions_applied": rc,
                }
                write_audit(audit_path, session_id, record, is_new_session, self.cfg.guard_model, self.cfg.timeout_ms, agent_name)
                return "BLOCK", block_reason

        # ── 7. Classify ───────────────────────────────────────────────────────────
        verdict, raw_output, latency_ms = classify(
            tool_name, redacted_text, self.cfg.guard_model, self.cfg.timeout_ms
        )

        # ── 8. Build and write audit record ───────────────────────────────────────
        block_reason = None
        if verdict == "BLOCK" and "-" in raw_output:
            block_reason = raw_output.split("-", 1)[-1].strip()
        elif verdict == "BLOCK":
            block_reason = raw_output

        record = {
            "schema_version":    "v1",
            "event_type":        "TOOL_CALL",
            "timestamp":         utcnow(),
            "session_id":        session_id,
            "agent":             agent_name,
            "skill_id":          skill_id,
            "hook_event":        hook_event,
            "tool_name":         tool_name,
            "tool_input":        redacted_input,
            "decoded_segments":  decoded_segments,
            "verdict":           verdict,
            "inspection_method": "LLM",
            "block_reason":      block_reason,
            "guard_model":       self.cfg.guard_model,
            "guard_raw_output":  raw_output,
            "latency_ms":        latency_ms,
            "redactions_applied": rc,
        }
        write_audit(audit_path, session_id, record, is_new_session, self.cfg.guard_model, self.cfg.timeout_ms, agent_name)

        return verdict, block_reason


def main() -> None:
    # ── 1. Parse stdin ────────────────────────────────────────────────────────
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session_id  = data.get("session_id", "unknown")
    hook_event  = data.get("hook_event_name", "PreToolUse")
    tool_name   = data.get("tool_name", "")
    tool_input  = data.get("tool_input", {})
    cwd         = data.get("cwd", "")
    tool_response = data.get("tool_response")

    is_gemini_flag, agent_name = detect_agent(hook_event, data.get("agent"))
    
    cfg = Config()
    engine = GuardEngine(cfg)
    
    if is_gemini_flag:
        adapter = GeminiAdapter(audit_only=cfg.audit_only)
    else:
        adapter = ClaudeAdapter(audit_only=cfg.audit_only)

    verdict, block_reason = engine.check_tool(
        tool_name=tool_name,
        tool_input=tool_input,
        agent_name=agent_name,
        session_id=session_id,
        cwd=cwd,
        hook_event=hook_event,
        tool_response=tool_response
    )

    if verdict == "BLOCK":
        adapter.block(block_reason or "Guard model block")

    adapter.allow()


if __name__ == "__main__":
    main()
