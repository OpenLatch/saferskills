import type { Story } from '@ladle/react'
import FrameworkBadges from '../../components/atoms/FrameworkBadges'

const all = [
  { family: 'owasp-llm', id: 'LLM01', label: 'Prompt Injection', url: 'https://genai.owasp.org/llmrisk/llm01-prompt-injection/' },
  { family: 'mitre-atlas', id: 'AML.T0051', label: 'LLM Prompt Injection', url: 'https://atlas.mitre.org/techniques/AML.T0051' },
  { family: 'cwe', id: 'CWE-78', label: 'OS Command Injection', url: 'https://cwe.mitre.org/data/definitions/78.html' },
] as const

export const All: Story = () => <FrameworkBadges frameworks={[...all]} />
export const OwaspOnly: Story = () => <FrameworkBadges frameworks={[all[0]]} />
export const Empty: Story = () => <FrameworkBadges frameworks={[]} />
