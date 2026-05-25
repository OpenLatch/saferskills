#!/usr/bin/env bash
# Stop hook: Type-check changed files when Claude finishes a turn
# Catches TypeScript and Python errors before Claude reports "done"
# Only runs the relevant checker based on which files actually changed

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0

# All uncommitted changes: modified + staged + untracked
changed=$(cd "$root" && {
  git diff --name-only 2>/dev/null
  git diff --cached --name-only 2>/dev/null
  git ls-files --others --exclude-standard 2>/dev/null
} | sort -u)

[ -z "$changed" ] && exit 0

errors=""
has_errors=0

# TypeScript: webapp/ or ui/ files changed → run tsc
if echo "$changed" | grep -qE '^(webapp|ui)/.*\.(ts|tsx)$'; then
  result=$(cd "$root/webapp" && pnpm tsc --noEmit 2>&1)
  if [ $? -ne 0 ]; then
    errors+="## TypeScript type errors (webapp)\n$(echo "$result" | head -20)\n\n"
    has_errors=1
  fi
fi

# Python: services/api/ files changed → auto-fix with ruff, then check for remaining errors
if echo "$changed" | grep -qE '^services/api/.*\.py$'; then
  # Auto-fix what ruff can fix (unused imports, formatting, etc.)
  cd "$root/services/api" && uv run ruff check . --fix --quiet 2>/dev/null
  # Check for remaining unfixable errors
  result=$(cd "$root/services/api" && uv run ruff check . 2>&1)
  if [ $? -ne 0 ]; then
    errors+="## Python lint errors (api)\n$(echo "$result" | head -20)\n\n"
    has_errors=1
  fi
fi

if [ $has_errors -eq 1 ]; then
  # Exit 2 = non-blocking: stderr is fed back to Claude so it can auto-fix.
  # Exit 1 would hard-block and require user intervention.
  cat >&2 <<HOOK_MSG
STOP HOOK: Type/lint errors detected in your changes. You MUST fix them now before responding to the user.

$(echo -e "$errors")
Action required: Read the erroring files, fix every reported error, then re-verify by running the relevant type-check command. Do NOT ask the user to fix these — fix them yourself.
HOOK_MSG
  exit 2
fi

exit 0
