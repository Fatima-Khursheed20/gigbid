import { Link } from 'react-router-dom'
import { Empty, ErrorState, Loading, PageHeader } from '../../components/States'
import { api, unwrap, type PipelineCard } from '../../lib/api/client'
import { useLoad } from '../../lib/hooks'

const STAGES = ['drafted', 'submitted', 'viewed', 'replied', 'interview', 'hired', 'lost'] as const

export default function PipelinePage() {
  const q = useLoad(async () => unwrap(await api.GET('/api/pipeline')), [], 10000)
  const cards = q.data ?? []
  return (
    <div>
      <PageHeader title="Pipeline" subtitle="Cards move as marketplace events arrive (polled by the worker every 2 minutes)." />
      {q.loading && <Loading />}
      {q.error && <ErrorState message={q.error} onRetry={q.reload} />}
      {!q.loading && !q.error && cards.length === 0 && <Empty title="Nothing in the pipeline yet">Approve a proposal to see it here.</Empty>}
      {cards.length > 0 && (
        <div className="flex gap-3 overflow-x-auto pb-3" data-testid="kanban">
          {STAGES.map((s) => {
            const col = cards.filter((c: PipelineCard) => c.stage === s)
            return (
              <section key={s} aria-label={s} className="w-64 shrink-0 rounded-xl bg-slate-100 p-2">
                <h2 className="mb-2 flex items-center justify-between px-1 text-sm font-semibold capitalize">{s}<span className="chip bg-white">{col.length}</span></h2>
                <ul className="space-y-2">
                  {col.map((c: PipelineCard) => (
                    <li key={c.proposal_id} className="card p-3 text-sm">
                      <Link to={c.stage === 'drafted' ? `/studio/${c.job_id}` : `/jobs/${c.job_id}`} className="font-medium hover:underline">{c.title ?? c.job_id}</Link>
                      <p className="mt-1 text-xs text-muted">{c.category} · ${c.amount?.toLocaleString() ?? '—'} · {c.connects ?? 0} ◆</p>
                    </li>
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
