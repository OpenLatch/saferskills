import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'default' | 'primary' | 'paper' | 'dark' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

interface BaseProps {
  variant?: Variant
  size?: Size
  children: ReactNode
  className?: string
}

type ButtonProps = BaseProps & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className'> & {
  as?: 'button'
  href?: never
}
type AnchorProps = BaseProps & {
  as: 'a'
  href: string
  target?: string
  rel?: string
  onClick?: (e: React.MouseEvent<HTMLAnchorElement>) => void
}

export type Props = ButtonProps | AnchorProps

/**
 * Hex-cap button. 4 variants × 3 sizes per the hi-fi shared.css `.btn` vocab.
 * Mobile (<640px) drops the hex mask for legibility (handled in components.css).
 */
export default function Button(props: Props) {
  const { variant = 'default', size = 'md', children, className = '' } = props
  const classes = [
    'btn',
    variant !== 'default' ? variant : '',
    size !== 'md' ? size : '',
    className,
  ].filter(Boolean).join(' ')

  if (props.as === 'a') {
    const { href, target, rel, onClick } = props
    return (
      <a className={classes} href={href} target={target} rel={rel} onClick={onClick}>
        {children}
      </a>
    )
  }

  const { as: _a, ...rest } = props as ButtonProps
  return (
    <button className={classes} {...rest}>
      {children}
    </button>
  )
}
