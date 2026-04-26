#!/usr/bin/env bash
# Detect webstack project state and emit a one-line hint to Claude Code's context.
# stdout from a SessionStart hook is appended to the session's system context.
set -euo pipefail

if [ -f .webstack/manifest.yaml ]; then
  echo "— webstack project detected. Run /webstack:feature to add a feature, /webstack:infra for infra changes, /webstack:deploy to deploy."
elif [ -f .webstack/SETUP.md ]; then
  echo "— webstack init partially complete. Read .webstack/SETUP.md, sign up for free-tier services, then run /webstack:infra."
fi
