#!/usr/bin/env python3
"""Block AI Read of .env* and secrets.local.* files.

Claude Code PreToolUse hook contract:
- Receive JSON on stdin: {tool_name, tool_input, ...}
- Exit 0 = allow; exit 2 with stderr message = block.
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
            sys.stderr.write(
                f"BLOCKED by webstack: {file_path} matches secret-file pattern "
                f"({pattern}). Source the file in your shell instead — see "
                f"docs/infrastructure/setup-guide.md.\n"
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
