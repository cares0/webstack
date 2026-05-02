#!/usr/bin/env python3
"""Block AI Read of .env* and secrets.local.* files.

Claude Code PreToolUse hook contract (current recommended pattern — JSON output):
- Receive JSON on stdin: {tool_name, tool_input, ...}
- Print a decision JSON object to stdout and exit 0.
- Schema: hookSpecificOutput.permissionDecision in {"allow","ask","deny","defer"}.
- Legacy "exit 2 + stderr" still works but is deprecated; we use JSON for richer feedback.
"""
import fnmatch
import json
import sys

BLOCKED_PATTERNS = [
    "**/.env",
    "**/.env.local",
    "**/.env.*.local",
    "**/secrets.local.*",
    ".env",
    ".env.local",
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
        return 0  # malformed input — let Claude Code surface its own error
    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return 0
    for pattern in BLOCKED_PATTERNS:
        if fnmatch.fnmatch(file_path, pattern):
            deny(
                f"BLOCKED by webstack: {file_path} matches secret-file pattern "
                f"({pattern}). Source the file in your shell instead — see "
                f"the plugin's docs/infrastructure/setup-guide.md."
            )
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
