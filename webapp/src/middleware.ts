import { defineMiddleware } from 'astro:middleware'
import { captureServerException } from '@/lib/server-observability'

export const onRequest = defineMiddleware(async (_context, next) => {
  try {
    return await next()
  } catch (error) {
    await captureServerException(error, 'ssr')
    throw error
  }
})
