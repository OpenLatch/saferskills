#!/usr/bin/env bash
# PreToolUse hook: Block edits to generated files
# Generated files must only be updated via the generation pipeline (schemas/ -> generate-models)

file_path=$(node -e "try{console.log(JSON.parse(process.env.TOOL_USE_INPUT).file_path||'')}catch{}" 2>/dev/null)

if [ -z "$file_path" ]; then
  exit 0
fi

# Normalize path separators for Windows
normalized=$(echo "$file_path" | tr '\\' '/')

if echo "$normalized" | grep -qE '/generated/'; then
  echo "BLOCKED: Never edit generated files directly." >&2
  echo "Modify the source schema in schemas/ and run the generation pipeline:" >&2
  echo "  Repo root: pnpm run generate" >&2
  exit 2
fi

exit 0
