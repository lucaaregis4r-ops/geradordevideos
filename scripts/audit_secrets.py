#!/usr/bin/env python3
"""Local secrets and credentials scanner.

Scans tracked git files and unstaged changes for exposed API keys, private keys,
and hardcoded tokens before committing.
"""

import re
import subprocess
import sys
from pathlib import Path

# Patterns indicating real secrets (not placeholders like 'your_api_key_here')
SECRET_PATTERNS = [
    (r"(?:sk-[a-zA-Z0-9]{20,})", "OpenAI / Anthropic Secret Key"),
    (r"(?:AKIA[0-9A-Z]{16})", "AWS Access Key ID"),
    (r"(?:ghp_[a-zA-Z0-9]{36})", "GitHub Personal Access Token"),
    (r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----)", "Private Key Header"),
    (r"(?:AIza[0-9A-Za-z\\-_]{35})", "Google API Key"),
    (r"(?:pexels_api_keys?\s*=\s*\[?['\"][a-zA-Z0-9]{40,}['\"])", "Pexels API Key"),
]

IGNORED_PATHS = {
    ".git",
    "storage",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
}

ALLOWLIST_TERMS = {
    "your_key", "mock", "dummy", "fake", "placeholder", "test_key", "test-token"
}


def scan_file(file_path: Path) -> list[tuple[int, str, str]]:
    findings = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    for line_no, line in enumerate(content.splitlines(), start=1):
        # Ignore comments or obvious tests
        lower_line = line.lower()
        if any(term in lower_line for term in ALLOWLIST_TERMS):
            continue

        for pattern, label in SECRET_PATTERNS:
            if re.search(pattern, line):
                findings.append((line_no, label, line.strip()[:60]))
    return findings


def main() -> int:
    # Get all tracked files from git
    try:
        tracked = subprocess.check_output(
            ["git", "ls-files"], text=True, stderr=subprocess.DEVNULL
        ).splitlines()
    except Exception:
        tracked = [str(p) for p in Path(".").rglob("*.py")]

    total_findings = 0
    for file_str in tracked:
        path = Path(file_str)
        if any(part in IGNORED_PATHS for part in path.parts):
            continue
        if not path.is_file():
            continue

        findings = scan_file(path)
        if findings:
            for line_no, label, sample in findings:
                print(f"[!] SECRET DETECTED in {path}:{line_no} [{label}]: {sample}", file=sys.stderr)
                total_findings += 1

    if total_findings > 0:
        print(f"\n[FAIL] Found {total_findings} potential secrets in tracked files!", file=sys.stderr)
        return 1

    print("[PASS] No exposed secrets detected in tracked files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
