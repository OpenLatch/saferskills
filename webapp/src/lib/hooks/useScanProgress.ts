import { useEffect, useReducer, useRef } from 'react'

import { env } from '@/env'
import { fetchScanRunById } from '@/lib/api/scans'

type StageId =
  | 'fetch'
  | 'index'
  | 'security'
  | 'supply_chain'
  | 'maintenance'
  | 'transparency'
  | 'community'
  | 'score'
  | 'sign'
  | 'done'

type Status = 'pending' | 'running' | 'completed' | 'failed'

interface ProgressEvent {
  event_seq: number
  stage: StageId
  completion_pct: number
  status: Status
  payload?: Record<string, unknown>
  timestamp?: string
}

export interface ScanProgressState {
  completionPct: number
  currentStage: StageId | 'none'
  status: 'idle' | 'connecting' | 'streaming' | 'polling' | 'completed' | 'failed'
  stageStatuses: Record<StageId, Status>
  events: ProgressEvent[]
  error: string | null
  lastEventSeq: number
}

type Action =
  | { type: 'connecting' }
  | { type: 'streaming' }
  | { type: 'polling' }
  | { type: 'progress'; payload: ProgressEvent }
  | { type: 'failure'; payload: string }
  | { type: 'completed' }

const emptyStages: Record<StageId, Status> = {
  fetch: 'pending',
  index: 'pending',
  security: 'pending',
  supply_chain: 'pending',
  maintenance: 'pending',
  transparency: 'pending',
  community: 'pending',
  score: 'pending',
  sign: 'pending',
  done: 'pending',
}

const initialState: ScanProgressState = {
  completionPct: 0,
  currentStage: 'none',
  status: 'idle',
  stageStatuses: { ...emptyStages },
  events: [],
  error: null,
  lastEventSeq: 0,
}

function reducer(state: ScanProgressState, action: Action): ScanProgressState {
  switch (action.type) {
    case 'connecting':
      return { ...state, status: 'connecting' }
    case 'streaming':
      return { ...state, status: 'streaming' }
    case 'polling':
      return { ...state, status: 'polling' }
    case 'progress': {
      const e = action.payload
      const next: ScanProgressState = {
        ...state,
        completionPct: Math.max(state.completionPct, e.completion_pct),
        currentStage: e.stage,
        stageStatuses: { ...state.stageStatuses, [e.stage]: e.status },
        events: [...state.events, e],
        lastEventSeq: Math.max(state.lastEventSeq, e.event_seq),
      }
      if (e.stage === 'done' && e.status === 'completed') next.status = 'completed'
      if (e.status === 'failed') next.status = 'failed'
      return next
    }
    case 'failure':
      return { ...state, status: 'failed', error: action.payload }
    case 'completed':
      return { ...state, status: 'completed', completionPct: 100 }
  }
}

export function useScanProgress(scanId: string | null) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const reconnectAttempts = useRef(0)
  const eventSourceRef = useRef<EventSource | null>(null)
  const pollingTimer = useRef<number | null>(null)

  // We intentionally do NOT depend on `state.status` — the effect captures the
  // scanId for the connect/poll closures, and the terminal-state short-circuit
  // is handled at dispatch time. Including state.status would tear down the
  // SSE connection on every progress event.
  useEffect(() => {
    if (!scanId) return undefined
    const activeScanId = scanId

    function clearPolling() {
      if (pollingTimer.current != null) {
        window.clearInterval(pollingTimer.current)
        pollingTimer.current = null
      }
    }

    function connect() {
      dispatch({ type: 'connecting' })
      const url = `${env.PUBLIC_API_URL}/api/v1/scans/${activeScanId}/events`
      const es = new EventSource(url)
      eventSourceRef.current = es

      es.addEventListener('progress', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data) as ProgressEvent
          dispatch({ type: 'progress', payload: data })
          if (data.stage === 'done' || data.status === 'failed') {
            es.close()
            eventSourceRef.current = null
          }
        } catch {
          // Ignore malformed events; SSE replay will fill in the missing rows.
        }
      })

      es.onopen = () => dispatch({ type: 'streaming' })

      es.onerror = () => {
        es.close()
        eventSourceRef.current = null
        if (reconnectAttempts.current < 3) {
          const delay = 1000 * 2 ** reconnectAttempts.current
          reconnectAttempts.current += 1
          window.setTimeout(connect, delay)
        } else {
          startPolling()
        }
      }
    }

    function startPolling() {
      dispatch({ type: 'polling' })
      pollingTimer.current = window.setInterval(async () => {
        try {
          const detail = await fetchScanRunById(activeScanId)
          if (!detail) return
          if (detail.status === 'completed' || detail.status === 'failed') {
            dispatch({ type: 'completed' })
            clearPolling()
          }
        } catch {
          // Polling errors are transient — retry next tick.
        }
      }, 1500)
    }

    connect()

    return () => {
      eventSourceRef.current?.close()
      eventSourceRef.current = null
      clearPolling()
    }
  }, [scanId])

  return state
}
