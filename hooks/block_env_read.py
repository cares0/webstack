#!/usr/bin/env python3
"""Block AI Read of .env* and secrets.local.* files.

Claude Code PreToolUse hook contract (current recommended pattern — JSON output):
- Receive JSON on stdin: {tool_name, tool_input, ...}
- Print a decision JSON object to stdout and exit 0.
- Schema: hookSpecificOutput.permissionDecision in {"allow","ask","deny","defer"}.
- Legacy "exit 2 + stderr" still works but is deprecated; we use JSON for richer feedback.

Coverage: any dotenv file (`.env`, `.env.local`, `.env.production`, `.env.development`,
`.env.<anything>`, `.env.*.local`) is blocked, EXCEPT non-secret variants ending in
`.template`/`.example`/`.sample`/`.dist`. This closes the gap where framework-specific
files like `.env.production` (Next.js) carry real secrets but were not covered by an
explicit `.env` / `.env.local` list.
"""
import fnmatch
import json
import os
import sys

# Safe, secret-free dotenv variants that remain readable.
ALLOWED_SUFFIXES = (".template", ".example", ".sample", ".dist")

# Non-dotenv secret files matched by basename glob.
EXPLICIT_GLOBS = ["secrets.local.*", "*.secret"]


def is_blocked(file_path: str) -> str:
    """Return the matched pattern/category if blocked, else ''."""
    name = os.path.basename(file_path)
    # Any dotenv file (.env or .env.<env>) is a secret carrier unless it's a template/example.
    if name == ".env" or name.startswith(".env."):
        if name.endswith(ALLOWED_SUFFIXES):
            return ""
        return name
    for pattern in EXPLICIT_GLOBS:
        if fnmatch.fnmatch(name, pattern):
            return pattern
    return ""


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
    matched = is_blocked(file_path)
    if matched:
        deny(
            f"BLOCKED by webstack: {file_path} is a secret-bearing file "
            f"(matched '{matched}'). Source it in your shell instead — see "
            f"the plugin's docs/infrastructure/setup-guide.md. "
            f"(.env.template / .env.example remain readable.)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
