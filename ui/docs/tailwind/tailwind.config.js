/**
 * Reference Tailwind config for SaferSkills.
 *
 * THIS FILE IS A DOCUMENTATION ARTIFACT, NOT THE RUNTIME CONFIG.
 *
 * The live SaferSkills `webapp/` uses Tailwind v4 with `@theme` directives in
 * `ui/styles/tokens.css` — there is no `tailwind.config.js` in the runtime.
 * This file mirrors the token shape as a familiar JS config for contributors
 * who prefer that form. Values MUST agree with `ui/styles/tokens.css` (the
 * single source of truth at runtime).
 *
 * Fonts are self-hosted via `@fontsource/{crimson-pro,manrope,jetbrains-mono}`
 * — never CDN-hosted.
 *
 * @type {import('tailwindcss').Config}
 */
module.exports = {
  darkMode: 'media', // SaferSkills follows `prefers-color-scheme`; flip to ['class'] if a toggle ever ships
  content: [
    './src/**/*.{js,ts,jsx,tsx,astro,mdx}',
    './pages/**/*.{js,ts,jsx,tsx,astro,mdx}',
    './components/**/*.{js,ts,jsx,tsx,astro,mdx}',
    '../ui/components/**/*.{ts,tsx}',
    '../ui/stories/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // ── Surface roles (Tailwind v4: bound via @theme from tokens.css)
        background: 'rgb(var(--background) / <alpha-value>)',
        foreground: 'rgb(var(--foreground) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        'muted-fg': 'rgb(var(--muted-fg) / <alpha-value>)',
        border: 'rgb(var(--border) / <alpha-value>)',

        // ── Brand
        primary: {
          DEFAULT: 'rgb(var(--primary) / <alpha-value>)',
          fg: 'rgb(var(--primary-fg) / <alpha-value>)',
          tint: 'rgb(var(--primary-tint) / <alpha-value>)',
        },

        // ── 4-band score palette (Methodology rubric)
        score: {
          green: 'rgb(var(--score-green) / <alpha-value>)',
          yellow: 'rgb(var(--score-yellow) / <alpha-value>)',
          orange: 'rgb(var(--score-orange) / <alpha-value>)',
          red: 'rgb(var(--score-red) / <alpha-value>)',
        },

        // Static brand cobalt (mode-independent). Use sparingly — prefer `primary` so dark mode flips.
        brand: {
          primary: '#1E40AF',
          primaryLightSurface: '#60A5FA',
          primaryTint: '#EFF6FF',
        },
      },
      borderRadius: {
        // Editorial Precision: 0px everywhere. `full` is the only escape hatch.
        none: '0',
        sm: '0',
        md: '0',
        lg: '0',
        xl: '0',
        '2xl': '0',
        full: '9999px',
      },
      fontFamily: {
        sans: ['Manrope', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        serif: ['Crimson Pro', 'Georgia', 'Times New Roman', 'serif'],
        display: ['Crimson Pro', 'Georgia', 'serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'SF Mono', 'monospace'],
      },
      fontSize: {
        // px-anchored — matches `--type-*` in tokens.css
        '2xs': ['11px', { lineHeight: '1.4' }],
        xs: ['12px', { lineHeight: '1.4' }],
        sm: ['14px', { lineHeight: '1.5' }],
        base: ['16px', { lineHeight: '1.5' }],
        lg: ['18px', { lineHeight: '1.6' }],
        xl: ['22px', { lineHeight: '1.3', letterSpacing: '-0.01em' }],
        '2xl': ['28px', { lineHeight: '1.25', letterSpacing: '-0.01em' }],
        '3xl': ['36px', { lineHeight: '1.2', letterSpacing: '-0.01em' }],
        hero: ['56px', { lineHeight: '1.05', letterSpacing: '-0.02em' }],
      },
      letterSpacing: {
        tight: '-0.02em',
        snug: '-0.01em',
        wide: '0.05em',
      },
      transitionTimingFunction: {
        // House easing — restrained, professional. No spring overshoot.
        default: 'cubic-bezier(0.32, 0, 0.67, 0)',
      },
      transitionDuration: {
        fast: '120ms',
        base: '200ms',
      },
      boxShadow: {
        // Editorial Precision: no shadows. Only `none` is provided so accidental
        // `shadow-sm` calls do not silently fall back to the Tailwind default.
        none: 'none',
        sm: 'none',
        DEFAULT: 'none',
        md: 'none',
        lg: 'none',
        xl: 'none',
        '2xl': 'none',
      },
    },
  },
  plugins: [],
};
