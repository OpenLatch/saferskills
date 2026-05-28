import Button from './Button'
import { flashToast } from './Toast'

interface Props {
  value: string
  label?: string
  className?: string
  size?: 'sm' | 'md'
  variant?: 'default' | 'paper' | 'primary' | 'dark'
  toastMessage?: string
}

/**
 * Click-to-copy wrapper around `<Button>`. Flashes the global toast on success.
 * Used by the install-command box, embed-badge box, scan-id footer.
 */
export default function CopyButton({
  value,
  label = 'Copy',
  className = '',
  size = 'sm',
  variant = 'paper',
  toastMessage = 'Copied to clipboard',
}: Props) {
  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(value)
      flashToast(toastMessage)
    } catch {
      flashToast('Copy failed — please copy manually')
    }
  }
  return (
    <Button
      size={size}
      variant={variant}
      onClick={onClick}
      className={className}
      aria-label={`Copy ${value}`}
    >
      {label}
    </Button>
  )
}
