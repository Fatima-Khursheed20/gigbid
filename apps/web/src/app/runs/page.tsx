import { Link, useSearchParams } from 'react-router-dom'
import { StatusChip } from '../../components/Badges'
import { Empty, ErrorState, Loading, PageHeader } from '../../components/States'
import { api, unwrap, type Run } from '../../lib/api/client'
import { useLoad } from '../../lib/hooks'

export default function RunsPage() {
  const [sp] = useSearchParams()
  const job = sp.get('job')
  const q = useLoad(async () => unwrap(await api.GET('/api/runs', { params: { query: { limit: 100 } } })), [], 5000)
  const runs = (q.data ?? []).filter((r: Run) => !job || r.job_id === job)
  const hist = useLoad(async () => (job ? unwrap(await api.GET('/api/jobs/{job_id}/history', { params: { path: { job_id: job } } })) : []), [job])

  async function replay(cp: string) {
    if (!job) return
    const r = unwrap(await api.POST('/api/jobs/{job_id}/replay/{checkpoint_id}', { params: { path: { job_id: job, checkpoint_id: cp } } }))
    window.location.href = `/runs/${r.run_id}`
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Agent runs" subtitle={job ? `Runs for ${job}` : 'Every graph run with latency, tokens and cost per node.'} />
      {q.loading && <Loading />}
      {q.error && <ErrorState message={q.error} onRetry={q.reload} />}
      {!q.loading && runs.length === 0 && <Empty title="No runs yet" />}
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="text-xs uppercase text-muted"><tr><th className="p-3">Run</th><th>Kind</th><th>Job</th><th>Status</th><th>Latency</th><th>Tokens</th><th>Cost</th></tr></thead>
          <tbody>
            {runs.map((r: Run) => (
              <tr key={r.id} className="border-t border-line">
                <td className="p-3"><Link className="text-brand underline" to={`/runs/${r.id}`}>{r.id}</Link></td>
                <td>{r.kind}</td><td className="max-w-48 truncate">{r.job_id ?? r.thread_id}</td><td><StatusChip status={r.status} /></td>
                <td className="tabular-nums">{r.latency_s ? `${r.latency_s.toFixed(1)}s` : '—'}</td>
                <td className="tabular-nums">{r.tokens ?? 0}</td><td className="tabular-nums">${(r.usd ?? 0).toFixed(5)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {job && (
        <section className="card p-4" aria-labelledby="cp-h">
          <h2 id="cp-h" className="font-semibold">Checkpoint history (replay from any node)</h2>
          {hist.loading ? <Loading /> : (
            <ol className="mt-2 space-y-1 text-sm">
              {(hist.data ?? []).map((c) => (
                <li key={c.checkpoint_id} className="flex flex-wrap items-center gap-2">
                  <span className="tabular-nums text-muted">step {c.step}</span>
                  <span>next: <code>{c.next.join(', ') || 'END'}</code></span>
                  <StatusChip status={c.status} />
                  {c.next.length > 0 && <button className="btn-ghost text-xs" onClick={() => replay(c.checkpoint_id)}>Replay from here</button>}
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  )
}
