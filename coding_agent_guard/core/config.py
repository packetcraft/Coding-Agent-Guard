import yaml
from pathlib import Path

DEFAULT_GUARD_MODEL  = "qwen2.5:1.5b"
DEFAULT_TIMEOUT_MS   = 5000
DEFAULT_AUDIT_PATH   = "./audit"
DEFAULT_ALLOWLIST_ON = True

class Config:
    def __init__(self):
        self.rules_dir = Path(__file__).parent.parent / "rules"
        self.config = self._load_yaml(self.rules_dir / "config.yaml").get("agentic", {})
        self.patterns = self._load_yaml(self.rules_dir / "patterns.yaml")

    def _load_yaml(self, path: Path) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    @property
    def guard_model(self) -> str:
        return str(self.config.get("guard_model", DEFAULT_GUARD_MODEL))

    @property
    def timeout_ms(self) -> int:
        return int(self.config.get("guard_timeout_ms", DEFAULT_TIMEOUT_MS))

    @property
    def audit_path(self) -> str:
        return str(self.config.get("audit_path", DEFAULT_AUDIT_PATH))

    @property
    def allowlist_enabled(self) -> bool:
        return bool(self.config.get("allowlist_enabled", DEFAULT_ALLOWLIST_ON))

    @property
    def allowlist_patterns(self) -> list[str]:
        return list(self.config.get("allowlist_patterns", []))

    @property
    def audit_only(self) -> bool:
        return bool(self.config.get("audit_only", False))

    @property
    def ipi_blocklist(self) -> list[str]:
        return self.patterns.get("ipi_blocklist", [])

    @property
    def protected_paths(self) -> list[str]:
        return self.patterns.get("protected_paths", [])
