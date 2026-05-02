#!/usr/bin/env bash
# Detect webstack project state by walking up from $PWD and emit a one-line hint.
# stdout from a SessionStart hook is appended to the session's system context.
set -euo pipefail

find_webstack_root() {
  local dir
  dir=$(pwd)
  while [ "$dir" != "/" ]; do
    if [ -d "$dir/.webstack" ]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir=$(dirname "$dir")
  done
  return 1
}

root=$(find_webstack_root || true)
if [ -z "${root:-}" ]; then
  exit 0
fi

if [ -f "$root/.webstack/manifest.yaml" ]; then
  if [ "$root" = "$(pwd)" ]; then
    echo "— webstack project detected at \$PWD. Run /webstack:feature to add a feature, /webstack:infra for infra changes, /webstack:deploy to deploy."
  else
    echo "— webstack project detected at $root (ancestor of \$PWD). Run /webstack:feature, /webstack:infra, or /webstack:deploy from $root."
  fi
elif [ -f "$root/.webstack/SETUP.md" ]; then
  echo "— webstack init partially complete at $root. Read $root/.webstack/SETUP.md, sign up for free-tier services, then run /webstack:infra."
fi
