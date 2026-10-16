/** Fail-closed projection: arbitrary SDK context and exception messages are never exported. */
const SAFE_PROPERTIES = new Set([
  'token', // Public project ingestion key required by the browser SDK.
  'product',
  'environment',
  'service',
  'release',
  '$exception_release',
  '$release_id',
  '$lib',
  '$lib_version',
  'distinct_id',
  '$device_id',
  '$session_id',
  '$window_id',
  '$process_person_profile',
  '$geoip_disable',
  'query_length_bucket',
  'artifact_source',
  'visibility',
  'filter_type',
  'action',
  'tier',
  'kind',
  'sub_score',
  'command_type',
  'format',
  'rule_id',
  'interaction',
  'count_bucket',
  'tab',
  'surface',
  'capture_source',
])
const ERROR_TYPES = new Set([
  'Error',
  'TypeError',
  'RangeError',
  'ReferenceError',
  'SyntaxError',
  'URIError',
  'EvalError',
  'AggregateError',
  'DOMException',
  'NetworkError',
])

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined
}

/** Only deployed application bundles qualify as source identifiers, never submitted files. */
function sourceFile(value: unknown): string | undefined {
  // Astro encodes dynamic route names with dots (for example `_.._abc.mjs`).
  // Reject traversal segments, not dots inside a legitimate bundle basename.
  if (typeof value !== 'string' || /(?:^|\/)\.\.(?:\/|$)/.test(value) || /[?#%]/.test(value)) return
  if (
    /^https?:\/\/(?:saferskills\.ai|www\.saferskills\.ai|staging\.saferskills\.ai|saferskills-webapp(?:-staging)?\.fly\.dev)\/_astro\/(?:[a-f\d]{40}\/)?[\w.-]+\.m?js$/.test(
      value
    )
  )
    return value
  // The Node SDK makes bundle filenames relative to /app before before_send runs.
  if (/^(?:(?:file:\/\/)?\/app\/(?:webapp\/)?)?dist\/server\/[\w./-]+\.m?js$/.test(value))
    return value
  return undefined
}

function exception(value: unknown): Record<string, unknown> | undefined {
  const input = record(value)
  if (!input) return
  const stack = record(input.stacktrace)
  const frames = Array.isArray(stack?.frames)
    ? stack.frames.slice(-40).flatMap((value) => {
        const frame = record(value)
        const filename = sourceFile(frame?.filename)
        if (!frame || !filename) return []
        return [
          {
            filename,
            platform: filename.startsWith('http') ? 'web:javascript' : 'node:javascript',
            ...(typeof frame.chunk_id === 'string' && /^[a-f\d-]{36}$/i.test(frame.chunk_id)
              ? { chunk_id: frame.chunk_id }
              : {}),
            ...(typeof frame.debug_id === 'string' && /^[a-f\d-]{36}$/i.test(frame.debug_id)
              ? { debug_id: frame.debug_id }
              : {}),
            ...(typeof frame.lineno === 'number' ? { lineno: frame.lineno } : {}),
            ...(typeof frame.colno === 'number' ? { colno: frame.colno } : {}),
            ...(typeof frame.function === 'string' && /^[\w.$<> ]{1,120}$/.test(frame.function)
              ? { function: frame.function }
              : {}),
          },
        ]
      })
    : []
  return {
    type: typeof input.type === 'string' && ERROR_TYPES.has(input.type) ? input.type : 'Error',
    value: '[redacted]',
    ...(frames.length ? { stacktrace: { type: 'raw', frames } } : {}),
  }
}

export function sanitizeTelemetryProperties(input: unknown): Record<string, unknown> | null {
  try {
    const properties = record(input)
    if (!properties) return null
    const result: Record<string, unknown> = { $geoip_disable: true, $process_person_profile: false }
    for (const [key, value] of Object.entries(properties)) {
      if (!SAFE_PROPERTIES.has(key)) continue
      if (typeof value === 'boolean' || typeof value === 'number') result[key] = value
      else if (typeof value === 'string' && /^[\w .$<>=+:-]{1,160}$/.test(value))
        result[key] = value
    }
    if (Array.isArray(properties.$exception_list)) {
      result.$exception_list = properties.$exception_list.slice(0, 5).flatMap((value) => {
        const clean = exception(value)
        return clean ? [clean] : []
      })
    }
    // SDK defaults and overrides cannot enable profiles or IP geolocation.
    result.$geoip_disable = true
    result.$process_person_profile = false
    return result
  } catch {
    return null
  }
}
