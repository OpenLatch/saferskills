import { z } from 'zod'

const envSchema = z.object({
  PUBLIC_API_URL: z.string().url().default('http://localhost:8000'),
  PUBLIC_POSTHOG_KEY: z.string().optional(),
  PUBLIC_POSTHOG_HOST: z.string().url().default('https://eu.posthog.com'),
  PUBLIC_SENTRY_DSN: z.string().optional(),
})

export const env = envSchema.parse({
  PUBLIC_API_URL: import.meta.env.PUBLIC_API_URL,
  PUBLIC_POSTHOG_KEY: import.meta.env.PUBLIC_POSTHOG_KEY,
  PUBLIC_POSTHOG_HOST: import.meta.env.PUBLIC_POSTHOG_HOST,
  PUBLIC_SENTRY_DSN: import.meta.env.PUBLIC_SENTRY_DSN,
})

export type Env = z.infer<typeof envSchema>
