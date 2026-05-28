import { forwardRef, type InputHTMLAttributes } from 'react'

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, 'prefix'> {
  prefix?: string
  className?: string
  containerClassName?: string
}

/**
 * Sharp form-field — 1px ink border, paper bg, mono prefix glyph, sans value.
 * Focus → border `--brand-primary` (teal). 0 border-radius.
 */
const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { prefix, className = '', containerClassName = '', ...rest },
  ref,
) {
  return (
    <label className={`input ${containerClassName}`.trim()}>
      {prefix && <span className="glyph" aria-hidden="true">{prefix}</span>}
      <input ref={ref} className={className} {...rest} />
    </label>
  )
})

export default Input
