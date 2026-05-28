export type SupportedAgent = {
  id: string
  name: string
  glyph: string
  installPath: string
  configPath: string
}

export const SUPPORTED_AGENTS: SupportedAgent[] = [
  {
    id: 'claude-code',
    name: 'Claude Code',
    glyph: 'CC',
    installPath: '~/.claude/skills/',
    configPath: '~/.claude/settings.json',
  },
  {
    id: 'cursor',
    name: 'Cursor',
    glyph: 'Cu',
    installPath: '~/.cursor/mcp.json',
    configPath: '~/.cursor/mcp.json',
  },
  {
    id: 'codex-cli',
    name: 'Codex CLI',
    glyph: 'Cx',
    installPath: '~/.codex/skills/',
    configPath: '~/.codex/skills/',
  },
  {
    id: 'copilot',
    name: 'GH Copilot',
    glyph: 'Co',
    installPath: '~/.github/copilot/',
    configPath: '~/.github/copilot/',
  },
  {
    id: 'windsurf',
    name: 'Windsurf',
    glyph: 'Wd',
    installPath: '~/.windsurf/',
    configPath: '~/.windsurf/',
  },
  {
    id: 'cline',
    name: 'Cline',
    glyph: 'Cl',
    installPath: 'vscode://extensions/cline',
    configPath: '(VS Code extension)',
  },
  {
    id: 'gemini-cli',
    name: 'Gemini CLI',
    glyph: 'Gm',
    installPath: '~/.gemini/config/',
    configPath: '~/.gemini/config/',
  },
  {
    id: 'openclaw',
    name: 'OpenClaw',
    glyph: 'OC',
    installPath: '~/.openclaw/skills/',
    configPath: 'openclaw.json',
  },
]

export const ATTACK_GRID = [
  {
    rule_id: 'SS-PLUGIN-SECRET-EXFIL-GH-TOKEN-01',
    category: 'CREDENTIAL EXFIL',
    title: 'GitHub PAT in source',
    severity: 'critical',
  },
  {
    rule_id: 'SS-MCP-POISON-UNICODE-TAG-01',
    category: 'PROMPT INJECTION',
    title: 'Unicode tag-channel injection',
    severity: 'critical',
  },
  {
    rule_id: 'SS-MCP-POISON-DESCRIPTION-CREEP-01',
    category: 'TOOL POISONING',
    title: 'MCP description creep',
    severity: 'critical',
  },
  {
    rule_id: 'SS-HOOKS-RCE-CURL-PIPE-01',
    category: 'REMOTE CODE EXECUTION',
    title: 'curl | bash in hook',
    severity: 'critical',
  },
  {
    rule_id: 'SS-MCP-SUPPLY-CHAIN-HASH-DRIFT-01',
    category: 'SUPPLY CHAIN',
    title: 'Hash drift (rug-pull)',
    severity: 'high',
  },
  {
    rule_id: 'SS-SKILL-TRANSPARENCY-LICENSE-01',
    category: 'TRANSPARENCY',
    title: 'Missing LICENSE',
    severity: 'medium',
  },
  {
    rule_id: 'SS-PLUGIN-SECRET-EXFIL-AWS-FILES-01',
    category: 'CREDENTIAL EXFIL',
    title: 'AWS credentials file read',
    severity: 'critical',
  },
  {
    rule_id: 'SS-MCP-POISON-SHADOW-TOOL-01',
    category: 'TOOL POISONING',
    title: 'MCP shadow tool',
    severity: 'critical',
  },
  {
    rule_id: 'SS-SKILL-INJECT-FENCED-RUN-01',
    category: 'PROMPT INJECTION',
    title: 'Fenced run-this imperative',
    severity: 'high',
  },
  {
    rule_id: 'SS-HOOKS-OBFUSCATION-B64-SHELL-01',
    category: 'OBFUSCATION',
    title: 'Base64-encoded shell payload',
    severity: 'high',
  },
  {
    rule_id: 'SS-MCP-SUPPLY-CHAIN-TYPOSQUAT-01',
    category: 'SUPPLY CHAIN',
    title: 'Typosquat candidate',
    severity: 'high',
  },
  {
    rule_id: 'SS-SKILL-MAINTENANCE-COMMIT-RECENCY-01',
    category: 'MAINTENANCE',
    title: 'Last commit > 180d',
    severity: 'medium',
  },
] as const

export type AttackGridEntry = (typeof ATTACK_GRID)[number]

export const INDEXED_COUNT = 12_847
export const REGISTRIES_COUNT = 12
