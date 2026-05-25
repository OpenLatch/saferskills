/// <reference types="astro/client" />

interface ImportMetaEnv {
  readonly PUBLIC_API_URL: string
  readonly PUBLIC_POSTHOG_KEY?: string
  readonly PUBLIC_POSTHOG_HOST?: string
  readonly PUBLIC_SENTRY_DSN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
