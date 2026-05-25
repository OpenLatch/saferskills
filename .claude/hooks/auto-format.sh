#!/usr/bin/env bash
# PostToolUse hook: Auto-format edited files with Biome (TS/JS/JSON) or Ruff (Python)
# Errors are reported to stderr so Claude Code can surface them.

file_path=$(node -e "try{console.log(JSON.parse(process.env.TOOL_USE_INPUT).file_path||'')}catch{}" 2>/dev/null)

if [ -z "$file_path" ]; then
  exit 0
fi

# Normalize path separators for Windows
normalized=$(echo "$file_path" | tr '\\' '/')

# Skip generated files — they have their own pipeline
if echo "$normalized" | grep -qE '/generated/'; then
  exit 0
fi

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0

# Python files → Ruff (any service directory)
if echo "$normalized" | grep -qE '\.py$'; then
  if echo "$normalized" | grep -qE 'services/[^/]+/'; then
    svc=$(echo "$normalized" | grep -oE 'services/[^/]+')
    cd "$root/$svc" 2>/dev/null || exit 0

    if ! uv run ruff format --quiet "$file_path" 2>&1; then
      echo "AUTO-FORMAT FAILED: ruff format failed on $file_path" >&2
    fi
    if ! uv run ruff check --fix --quiet "$file_path" 2>&1; then
      echo "AUTO-FORMAT WARNING: ruff check --fix had unfixable issues on $file_path" >&2
    fi
  fi
  exit 0
fi

# TS/JS/JSON files → Biome
if echo "$normalized" | grep -qE '\.(ts|tsx|js|jsx|json)$'; then
  # Skip node_modules / lock files
  if echo "$normalized" | grep -qE '(node_modules|pnpm-lock|package-lock)'; then
    exit 0
  fi

  # Determine which project owns this file
  if echo "$normalized" | grep -qE '(webapp/|ui/)'; then
    cd "$root/webapp" 2>/dev/null || exit 0
    if ! pnpm biome check --write --no-errors-on-unmatched "$file_path" 2>&1; then
      echo "AUTO-FORMAT FAILED: biome check failed on $file_path" >&2
    fi
  fi
  exit 0
fi

exit 0
