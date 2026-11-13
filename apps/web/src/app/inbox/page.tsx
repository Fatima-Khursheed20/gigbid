import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ActionBadge, FitBar, RiskBadge, StatusChip } from '../../components/Badges'
import { Empty, ErrorState, Loading, PageHeader } from '../../components/States'
import { api, unwrap, type InboxItem } from '../../lib/api/client'
import { useLoad } from '../../lib/hooks'

const FILTERS = [['all', 'All'], ['bid', 'Recommended'], ['awaiting_approval', 'Awaiting approval'], ['skip', 'Skipped']] as const

export default function InboxPage() {
  const [filter, setFilter] = useState<string>('all')
  const [msg, setMsg] = useState<string | null>(null)
  const q = useLoad(async () => unwrap(await api.GET('/api/jobs')), [], 8000)
  const items = (q.data ?? []).filter((j: InboxItem) => filter === 'all' || j.action === filter || j.status === filter)

  async function scout() {
    try { unwrap(await api.POST('/api/jobs/scout')); setMsg('Scouting saved searches… new jobs appear here as they are analysed.') }
    catch (e) { setMsg(e instanceof Error ? e.message : String(e)) }
  }
  async function skip(id: string) { await api.POST('/api/jobs/{job_id}/skip', { params: { path: { job_id: id } } }); q.reload() }

  return (
    <div>
      <PageHeader title="Job inbox" subtitle="New jobs ranked by fit, with risk, recommended action, price and Connects cost."
        actions={<button className="btn-primary" onClick={scout} data-testid="scout-now">Scout now</button>} />
      {msg && <p className="mb-3 text-sm text-muted" role="status">{msg}</p>}
      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Filter jobs">
        {FILTERS.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={filter === k} className={filter === k ? 'btn-primary' : 'btn-ghost'} onClick={() => setFilter(k)}>{l}</button>
        ))}
      </div>
      {q.loading && <Loading />}
      {q.error && <ErrorState message={q.error} onRetry={q.reload} />}
      {!q.loading && !q.error && items.length === 0 && (
        <Empty title="No jobs yet">Your saved searches run on a schedule. Press “Scout now” to fetch jobs immediately.</Empty>
      )}
      <ul className="space-y-2" data-testid="inbox-list">
        {items.map((j: InboxItem) => (
          <li key={j.job_id} className="card flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1">
              <Link to={`/jobs/${j.job_id}`} className="font-medium hover:underline">{j.title}</Link>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                <span>{j.category ?? '—'}</span>
                <RiskBadge risk={j.risk} scam={j.scam} injection={j.injection} />
                <StatusChip status={j.status} />
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <FitBar fit={j.fit} />
              <ActionBadge action={j.action} />
              <span className="tabular-nums">{j.price ? `$${j.price.toLocaleString()}${j.bid_type === 'hourly' ? '/h' : ''}` : '—'}</span>
              <span className="tabular-nums text-muted" title="Connects to submit">{j.connects ?? '—'} ◆</span>
              <div className="flex gap-2">
                {j.status === 'awaiting_approval'
                  ? <Link className="btn-primary" to={`/studio/${j.job_id}`}>Review draft</Link>
                  : <Link className="btn-ghost" to={`/jobs/${j.job_id}`}>Open</Link>}
                {j.action !== 'skip' && j.status !== 'submitted' && <button className="btn-ghost" onClick={() => skip(j.job_id)} aria-label={`Skip ${j.title}`}>Skip</button>}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
