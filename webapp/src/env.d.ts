/// <reference types="astro/client" />

interface ImportMetaEnv {
  readonly PUBLIC_API_URL: string;
  readonly PUBLIC_RESEND_AUDIENCE_ID?: string;
  readonly PUBLIC_POSTHOG_KEY?: string;
  readonly PUBLIC_POSTHOG_HOST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
