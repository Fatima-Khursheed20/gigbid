import { useCallback, useEffect, useRef, useState } from 'react'

/** Load data with explicit loading / error / empty states; optional polling. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[], pollMs?: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const reload = useCallback(async () => {
    try {
      setData(await fnRef.current())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    reload()
    if (!pollMs) return
    const t = setInterval(reload, pollMs)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, error, loading, reload, setData }
}

export type RunEvent = {
  kind: string
  node?: string
  ts?: number
  latency_s?: number
  tokens?: number
  usd?: number
  status?: string
  tool?: string
  error?: string
  models?: string[]
  [k: string]: unknown
}

/** Live node-by-node progress from LangGraph via Server-Sent Events. */
export function useRunStream(runId: string | null | undefined, onEnd?: (status: string) => void) {
  const [events, setEvents] = useState<RunEvent[]>([])
  const [status, setStatus] = useState<string>('connecting')
  const endRef = useRef(onEnd)
  endRef.current = onEnd

  useEffect(() => {
    if (!runId) return
    setEvents([])
    setStatus('streaming')
    // EventSource cannot set headers: the same-origin httpOnly session cookie authenticates the stream
    // (tokens are never put in URLs, where they would end up in access logs).
    const es = new EventSource(`/api/runs/${runId}/stream`, { withCredentials: true })
    es.addEventListener('node', (m) => {
      try { setEvents((prev) => [...prev, JSON.parse((m as MessageEvent).data)]) } catch { /* ignore */ }
    })
    es.addEventListener('end', (m) => {
      let s = 'done'
      try { s = JSON.parse((m as MessageEvent).data).status ?? 'done' } catch { /* ignore */ }
      setStatus(s)
      endRef.current?.(s)
      es.close()
    })
    es.onerror = () => { setStatus((s) => (s === 'streaming' ? 'reconnecting' : s)) }
    return () => es.close()
  }, [runId])

  return { events, status }
}
