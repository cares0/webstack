#!/usr/bin/env python3
"""Block Bash commands that would leak secrets from .env or environment.

Claude Code PreToolUse hook contract (current recommended pattern — JSON output):
- Receive JSON on stdin: {tool_name, tool_input, ...}
- Print a decision JSON object to stdout and exit 0.
- Legacy "exit 2 + stderr" still works but is deprecated; we use JSON for richer feedback.
"""
import json
import re
import sys

# Fast-path: if this regex doesn't match the command, skip the heavier scan
# below. Every BLOCKED_PATTERNS regex requires at least one of these tokens,
# so any command without them is guaranteed not to match. `\benv\b` covers
# `env` and `env|grep` while ignoring "development", "environment", etc.
FAST_PATH_RE = re.compile(
    r"\benv\b|\.env|printenv|TOKEN|KEY|SECRET|PASSWORD|\$"
)

BLOCKED_PATTERNS = [
    re.compile(r"(?:^|\s)(?:cat|head|tail|less|more|bat)\s+[^\s]*\.env\b"),
    re.compile(r"\bprintenv\s+[A-Za-z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD)\b"),
    re.compile(r"^\s*env(\s|$)"),
    re.compile(r"\benv\s*\|\s*grep"),
    re.compile(r"\becho\s+\$[A-Za-z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD)\b"),
]


def deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.stdout.flush()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        return 0
    # Fast-path: bail before the heavier scan if no suspicious token appears.
    if not FAST_PATH_RE.search(command):
        return 0
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(command):
            deny(
                "BLOCKED by webstack: command would expose secrets. "
                "Source .env in your shell directly; AI must not read tokens."
            )
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
