import { Link, useParams } from 'react-router-dom'
import { StatusChip } from '../../../components/Badges'
import { RunTimeline } from '../../../components/RunTimeline'
import { ErrorState, Loading, PageHeader } from '../../../components/States'
import { api, unwrap } from '../../../lib/api/client'
import { useLoad, useRunStream, type RunEvent } from '../../../lib/hooks'

export default function RunViewerPage() {
  const { id = '' } = useParams()
  const q = useLoad(async () => unwrap(await api.GET('/api/runs/{run_id}', { params: { path: { run_id: id } } })), [id])
  const live = ['queued', 'running'].includes(q.data?.status ?? '')
  const stream = useRunStream(live ? id : null, () => q.reload())
  if (q.loading) return <Loading />
  if (q.error) return <ErrorState message={q.error} onRetry={q.reload} />
  const r = q.data!
  const events = (live ? stream.events : (r.events as RunEvent[]))
  const byNode = (r.by_node ?? {}) as Record<string, { calls: number; tokens: number; usd: number; latency_s: number }>
  return (
    <div className="space-y-5">
      <PageHeader title={`Run ${r.id}`} subtitle={<span className="flex flex-wrap items-center gap-2"><StatusChip status={live ? stream.status : r.status} />
        {r.kind} · {r.job_id && <Link className="text-brand underline" to={`/jobs/${r.job_id}`}>{r.job_id}</Link>} · {r.latency_s?.toFixed(1) ?? '…'}s · {r.tokens ?? 0} tokens · ${(r.usd ?? 0).toFixed(5)}</span>}
        actions={r.trace_url ? <a className="btn-ghost" href={r.trace_url} target="_blank" rel="noreferrer">Full trace (LangSmith) ↗</a> : undefined} />
      <p className="text-xs text-muted">Trace id <code>{r.trace_id ?? '—'}</code> — the same id is attached to every MCP call and audit-log row of this run.</p>
      <RunTimeline events={events} status={live ? stream.status : r.status} />
      {Object.keys(byNode).length > 0 && (
        <section className="card overflow-x-auto p-4">
          <h2 className="font-semibold">LLM usage by node</h2>
          <table className="mt-2 w-full text-left text-sm"><thead className="text-xs uppercase text-muted"><tr><th>Node</th><th>Calls</th><th>Tokens</th><th>USD</th><th>LLM time</th></tr></thead>
            <tbody>{Object.entries(byNode).map(([n, v]) => <tr key={n} className="border-t border-line"><td className="py-1">{n}</td><td>{v.calls}</td><td>{v.tokens}</td><td>${v.usd.toFixed(5)}</td><td>{v.latency_s}s</td></tr>)}</tbody></table>
        </section>
      )}
      {r.error && <ErrorState message={r.error} />}
    </div>
  )
}
