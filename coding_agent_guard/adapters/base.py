import json
import sys

def exit_allow(is_gemini: bool) -> None:
    if is_gemini:
        print(json.dumps({"decision": "allow"}))
    sys.exit(0)


def exit_block(is_gemini: bool, reason: str, audit_only: bool) -> None:
    if audit_only:
        sys.stderr.write(f"[coding-agent-guard] AUDIT: would have blocked — {reason}\n")
        exit_allow(is_gemini)
    else:
        sys.stderr.write(f"[coding-agent-guard] BLOCK: {reason}\n")
        if is_gemini:
            print(json.dumps({"decision": "deny", "reason": reason}))
            sys.exit(0)
        else:
            sys.exit(2)

def detect_agent(hook_event: str, agent_name: str | None) -> tuple[bool, str]:
    is_gemini = hook_event in ["BeforeTool", "AfterTool"]
    if not agent_name:
        agent_name = "Gemini" if is_gemini else "Claude"
    return is_gemini, agent_name

def normalize_hook_event(hook_event: str) -> str:
    if hook_event == "BeforeTool":
        return "PreToolUse"
    elif hook_event == "AfterTool":
        return "PostToolUse"
    return hook_event
