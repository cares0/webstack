#!/usr/bin/env python3
"""Block Bash commands that would leak secrets from .env or environment.

Claude Code PreToolUse hook contract:
- Receive JSON on stdin: {tool_name, tool_input, ...}
- Exit 0 = allow; exit 2 with stderr message = block.
"""
import json
import re
import sys

BLOCKED_PATTERNS = [
    re.compile(r"(?:^|\s)(?:cat|head|tail|less|more|bat)\s+[^\s]*\.env\b"),
    re.compile(r"\bprintenv\s+[A-Za-z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD)\b"),
    re.compile(r"^\s*env(\s|$)"),
    re.compile(r"\benv\s*\|\s*grep"),
    re.compile(r"\becho\s+\$[A-Za-z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD)\b"),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        return 0
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(command):
            sys.stderr.write(
                "BLOCKED by webstack: command would expose secrets. "
                "Source .env in your shell directly; AI must not read tokens.\n"
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
