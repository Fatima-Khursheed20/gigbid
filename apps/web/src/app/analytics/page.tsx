import { ErrorState, Loading, PageHeader } from '../../components/States'
import { api, unwrap } from '../../lib/api/client'
import { useLoad } from '../../lib/hooks'

type Num = number | null | undefined
const pct = (v: Num) => (v == null ? '—' : `${Math.round(v * 100)}%`)
const n2 = (v: Num, d = 1) => (v == null ? '—' : Number(v).toFixed(d))

export default function AnalyticsPage() {
  const q = useLoad(async () => unwrap(await api.GET('/api/analytics')), [], 20000)
  if (q.loading) return <Loading />
  if (q.error) return <ErrorState message={q.error} onRetry={q.reload} />
  const a = q.data!
  const cl = a.cost_latency as { all_runs?: Record<string, Num>; proposal_runs?: Record<string, Num>; declared?: Record<string, Num> }
  const con = a.connects as Record<string, Num>
  const tiles: [string, string][] = [
    ['Jobs analysed', String(a.funnel.seen ?? 0)], ['Recommended bids', String(a.funnel.recommended_bid ?? 0)],
    ['Scams flagged', String(a.funnel.scams_flagged ?? 0)], ['Connects spent', String(con.spent ?? 0)],
    ['Connects per reply', n2(con.connects_per_reply)], ['p95 latency / proposal', `${n2(cl.proposal_runs?.p95)}s`],
  ]
  const maxRate = Math.max(0.01, ...a.by_category.map((c) => Number(c.reply_rate ?? 0)))
  return (
    <div className="space-y-5">
      <PageHeader title="Analytics" subtitle="Outcomes from the marketplace, cost and latency from the run ledger." />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {tiles.map(([l, v]) => <div key={l} className="card p-3"><p className="text-xs text-muted">{l}</p><p className="mt-1 text-xl font-bold tabular-nums">{v}</p></div>)}
      </div>
      <section className="card p-4" aria-labelledby="cat-h">
        <h2 id="cat-h" className="font-semibold">Reply and hire rate by category</h2>
        {a.by_category.length === 0 ? <p className="mt-2 text-sm text-muted">No submitted proposals yet.</p> : (
          <ul className="mt-3 space-y-2">
            {a.by_category.map((c) => (
              <li key={String(c.category)} className="grid grid-cols-[6rem_1fr_9rem] items-center gap-3 text-sm">
                <span>{String(c.category)}</span>
                <div className="h-3 rounded bg-slate-100" aria-hidden><div className="h-3 rounded bg-brand" style={{ width: `${(Number(c.reply_rate ?? 0) / maxRate) * 100}%` }} /></div>
                <span className="tabular-nums">reply {pct(c.reply_rate as Num)} · hire {pct(c.hire_rate as Num)} <span className="text-muted">(n={String(c.submitted)})</span></span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="card p-4 text-sm" aria-labelledby="cost-h">
          <h2 id="cost-h" className="font-semibold">Cost and latency vs declared budgets</h2>
          <table className="mt-2 w-full"><tbody>
            <tr><td className="text-muted">Runs measured</td><td className="tabular-nums">{String(cl.all_runs?.runs ?? 0)}</td></tr>
            <tr><td className="text-muted">p50 / p95 latency (all runs)</td><td className="tabular-nums">{n2(cl.all_runs?.p50)}s / {n2(cl.all_runs?.p95)}s</td></tr>
            <tr><td className="text-muted">Avg cost per run</td><td className="tabular-nums">${n2(cl.all_runs?.avg_usd, 5)}</td></tr>
            <tr><td className="text-muted">Avg cost per proposal</td><td className="tabular-nums">${n2(cl.proposal_runs?.avg_usd, 5)}</td></tr>
            <tr><td className="text-muted">Declared p95 per proposal</td><td className="tabular-nums">{String(cl.declared?.p95_latency_s_per_proposal)}s</td></tr>
            <tr><td className="text-muted">Declared cost per proposal</td><td className="tabular-nums">${String(cl.declared?.usd_per_proposal)}</td></tr>
          </tbody></table>
        </section>
        <section className="card p-4 text-sm" aria-labelledby="rej-h">
          <h2 id="rej-h" className="font-semibold">Top rejection reasons</h2>
          {a.rejection_reasons.length === 0 ? <p className="mt-2 text-muted">No rejected drafts yet.</p> :
            <ol className="mt-2 list-decimal pl-5">{a.rejection_reasons.map((r) => <li key={String(r.reason)}>{String(r.reason)} <span className="text-muted">×{String(r.n)}</span></li>)}</ol>}
        </section>
      </div>
    </div>
  )
}
