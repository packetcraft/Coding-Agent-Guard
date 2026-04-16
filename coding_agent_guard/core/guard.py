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
from coding_agent_guard.adapters.base import detect_agent, normalize_hook_event
from coding_agent_guard.adapters.claude import ClaudeAdapter
from coding_agent_guard.adapters.gemini import GeminiAdapter

def main() -> None:
    # ── 1. Parse stdin ────────────────────────────────────────────────────────
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # Malformed payload — fail open

    session_id  = data.get("session_id", "unknown")
    hook_event  = data.get("hook_event_name", "PreToolUse")
    tool_name   = data.get("tool_name", "")
    tool_input  = data.get("tool_input", {})
    cwd         = data.get("cwd", "")

    is_gemini_flag, agent_name = detect_agent(hook_event, data.get("agent"))
    hook_event = normalize_hook_event(hook_event)

    # ── 2. Load config ────────────────────────────────────────────────────────
    cfg = Config()
    
    # Initialize appropriate adapter
    if is_gemini_flag:
        adapter = GeminiAdapter(audit_only=cfg.audit_only)
    else:
        adapter = ClaudeAdapter(audit_only=cfg.audit_only)

    _cwd_path = Path(cwd) if cwd else Path.cwd()
    if not _cwd_path.is_dir():
        _cwd_path = Path.cwd()
    audit_path = (_cwd_path / cfg.audit_path).resolve()

    # ── 3. Detect new session (before any writes) ─────────────────────────────
    is_new_session = not (audit_path / f"{session_id}.jsonl").exists()
    if is_new_session and cfg.audit_only:
        sys.stderr.buffer.write(
            "[coding-agent-guard] WARNING: audit_only=true -- guard is logging but NOT blocking.\n".encode("utf-8")
        )

    # ── 4. PostToolUse — scan command output for exfiltration signals ─────────
    if hook_event == "PostToolUse":
        output_text = str(data.get("tool_response", ""))

        # 4a. Fast-path: IPI regex blocklist
        for pattern_str in cfg.ipi_blocklist:
            pattern = re.compile(pattern_str)
            if pattern.search(output_text):
                raw_output = f"BLOCK - Fast-path regex match: {pattern.pattern}"
                latency_ms = 0
                redacted_output, redaction_count = redact(truncate_output(output_text))
                record = {
                    "schema_version":    "v1",
                    "event_type":        "TOOL_CALL",
                    "timestamp":         utcnow(),
                    "session_id":        session_id,
                    "agent":             agent_name,
                    "hook_event":        hook_event,
                    "tool_name":         tool_name,
                    "tool_input":        {"output_preview": redacted_output[:500]},
                    "verdict":           "BLOCK_AUDITED",  # detected but not enforced — PostToolUse cannot block
                    "inspection_method": "REGEX",
                    "block_reason":      "Prompt injection detected via fast-path regex.",
                    "guard_model":       None,
                    "guard_raw_output":  raw_output,
                    "latency_ms":        latency_ms,
                    "redactions_applied": redaction_count,
                }
                write_audit(audit_path, session_id, record, is_new_session, cfg.guard_model, cfg.timeout_ms, agent_name)
                adapter.allow()

        # 4b. Slow-path: Ollama classification (with truncation)
        truncated_output = truncate_output(output_text)
        redacted_output, redaction_count = redact(truncated_output)

        verdict, raw_output, latency_ms = classify(
            f"{tool_name}:output", redacted_output, cfg.guard_model, cfg.timeout_ms, hook_event="PostToolUse"
        )
        # PostToolUse cannot block — remap BLOCK to BLOCK_AUDITED so the audit
        # log accurately reflects "detected but not enforced".
        audited_verdict = "BLOCK_AUDITED" if verdict == "BLOCK" else verdict
        record = {
            "schema_version":    "v1",
            "event_type":        "TOOL_CALL",
            "timestamp":         utcnow(),
            "session_id":        session_id,
            "agent":             agent_name,
            "hook_event":        hook_event,
            "tool_name":         tool_name,
            "tool_input":        {"output_preview": redacted_output[:500]},
            "verdict":           audited_verdict,
            "inspection_method": "LLM",
            "block_reason":      "Prompt injection detected via LLM guard." if audited_verdict == "BLOCK_AUDITED" else None,
            "guard_model":       cfg.guard_model,
            "guard_raw_output":  raw_output,
            "latency_ms":        latency_ms,
            "redactions_applied": redaction_count,
        }

        write_audit(audit_path, session_id, record, is_new_session, cfg.guard_model, cfg.timeout_ms, agent_name)
        adapter.allow()  # PostToolUse is always observation-only — no blocking

    # ── 5. PreToolUse — allowlist check (Bash only) ───────────────────────────
    if cfg.allowlist_enabled and tool_name.lower() in ["bash", "sh"]:
        command = tool_input.get("command", "")
        if is_allowlisted(command, cfg.allowlist_patterns):
            record = {
                "schema_version":    "v1",
                "event_type":        "TOOL_CALL",
                "timestamp":         utcnow(),
                "session_id":        session_id,
                "agent":             agent_name,
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
            write_audit(audit_path, session_id, record, is_new_session, cfg.guard_model, cfg.timeout_ms, agent_name)
            adapter.allow()

    # ── 5.5 Protected path check (Write/Edit only) ───────────────────────────
    if any(k in tool_name.lower() for k in ["write", "edit", "patch"]):
        file_path = str(tool_input.get("file_path", ""))
        # Normalize: replace backslashes and strip leading ./
        norm_path = file_path.replace("\\", "/").lstrip("./")
        if any(norm_path.endswith(p) for p in cfg.protected_paths):
            block_reason = f"Security: modifying protected hook configuration is forbidden ({file_path})"
            record = {
                "schema_version":    "v1",
                "event_type":        "TOOL_CALL",
                "timestamp":         utcnow(),
                "session_id":        session_id,
                "agent":             agent_name,
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
            write_audit(audit_path, session_id, record, is_new_session, cfg.guard_model, cfg.timeout_ms, agent_name)
            adapter.block(block_reason)

    # ── 6. Redact secrets ─────────────────────────────────────────────────────
    inspectable_text, decoded_segments = extract_inspectable(tool_name, tool_input)
    redacted_text, _    = redact(inspectable_text)
    redacted_input, rc  = redact_dict(tool_input)

    # ── 7. Classify ───────────────────────────────────────────────────────────
    verdict, raw_output, latency_ms = classify(
        tool_name, redacted_text, cfg.guard_model, cfg.timeout_ms
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
        "hook_event":        hook_event,
        "tool_name":         tool_name,
        "tool_input":        redacted_input,
        "decoded_segments":  decoded_segments,
        "verdict":           verdict,
        "inspection_method": "LLM",
        "block_reason":      block_reason,
        "guard_model":       cfg.guard_model,
        "guard_raw_output":  raw_output,
        "latency_ms":        latency_ms,
        "redactions_applied": rc,
    }
    write_audit(audit_path, session_id, record, is_new_session, cfg.guard_model, cfg.timeout_ms, agent_name)

    # ── 9. Exit ───────────────────────────────────────────────────────────────
    if verdict == "BLOCK":
        adapter.block(block_reason or "Guard model block")

    adapter.allow()  # ALLOW or ERROR — both fail open


if __name__ == "__main__":
    main()
