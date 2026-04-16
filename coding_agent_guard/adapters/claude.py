from coding_agent_guard.adapters.base import exit_allow, exit_block

class ClaudeAdapter:
    def __init__(self, audit_only: bool = False):
        self.audit_only = audit_only
        self.is_gemini = False

    def allow(self):
        exit_allow(self.is_gemini)

    def block(self, reason: str):
        exit_block(self.is_gemini, reason, self.audit_only)
