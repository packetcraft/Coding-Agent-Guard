import re
import yaml
from pathlib import Path
from typing import Any

from coding_agent_guard.core.config import Config


class StaticScanner:
    """
    Engine for scanning codebases and payloads for malicious patterns.
    """

    def __init__(self, rules_path: Path | None = None):
        cfg = Config()
        root = Path(__file__).parent.parent
        self.rules_path = rules_path or (root / "rules" / "static_analysis.yaml")
        self.rules = self._load_rules()

    def _load_rules(self) -> list[dict[str, Any]]:
        if not self.rules_path.exists():
            print(f"[!] Warning: Rules file not found at {self.rules_path}")
            return []
        
        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("rules", [])
        except Exception as e:
            print(f"[!] Error loading rules: {e}")
            return []

    def scan_content(self, content: str, source_name: str = "unknown") -> list[dict[str, Any]]:
        """Scan a string for matches against the rules."""
        findings = []
        for rule in self.rules:
            pattern = rule.get("pattern")
            if not pattern:
                continue
            
            try:
                if re.search(pattern, content):
                    findings.append({
                        "rule_id": rule.get("id"),
                        "category": rule.get("category"),
                        "severity": rule.get("severity"),
                        "description": rule.get("description"),
                        "source": source_name
                    })
            except re.error as e:
                print(f"[!] Regex error in rule {rule.get('id')}: {e}")
        
        return findings

    def scan_file(self, file_path: Path) -> list[dict[str, Any]]:
        """Scan a single file."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return self.scan_content(content, source_name=str(file_path))
        except Exception as e:
            print(f"[!] Error scanning file {file_path}: {e}")
            return []

    def scan_directory(self, dir_path: Path, recursive: bool = True) -> list[dict[str, Any]]:
        """Scan a directory for sensitive files and patterns."""
        all_findings = []
        pattern = "**/*" if recursive else "*"
        
        for p in dir_path.glob(pattern):
            if p.is_file() and not p.name.startswith("."):
                # Skip large files or binary files if necessary
                if p.stat().st_size > 1_000_000: # 1MB limit for safety
                    continue
                
                all_findings.extend(self.scan_file(p))
        
        return all_findings


def cli():
    """Entry point for `coding-agent-guard scan`."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="coding-agent-guard scan",
        description="Static analysis security scanner for AI agents.",
    )
    parser.add_argument("path", help="Path to scan (file or directory)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument("--recursive", action="store_true", help="Scan directories recursively")

    args = parser.parse_args()
    scanner = StaticScanner()
    path = Path(args.path)

    if not path.exists():
        print(f"[!] Path does not exist: {path}")
        return

    findings = []
    if path.is_file():
        findings = scanner.scan_file(path)
    else:
        findings = scanner.scan_directory(path, recursive=args.recursive)

    if args.format == "json":
        print(json.dumps(findings, indent=2))
    else:
        print(f"[*] Scan complete. Found {len(findings)} issues.")
        if findings:
            print("-" * 70)
            for f in findings:
                sev = f.get("severity", "INFO")
                print(f"[{sev}] {f.get('rule_id')}: {f.get('description')}")
                print(f"      Source: {f.get('source')}")
                print("-" * 70)
