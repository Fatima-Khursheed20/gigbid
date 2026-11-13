import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ActionBadge, FitBar, RiskBadge, StatusChip } from '../../../components/Badges'
import { RunTimeline } from '../../../components/RunTimeline'
import { ErrorState, Loading, PageHeader } from '../../../components/States'
import { ApiError, api, unwrap } from '../../../lib/api/client'
import { useLoad, useRunStream } from '../../../lib/hooks'

type Row = { requirement: string; status: string; evidence: { evidence_id: string; project?: string; type?: string; snippet?: string }[] }

export default function JobDetailPage() {
  const { id = '' } = useParams()
  const [runId, setRunId] = useState<string | null>(null)
  const q = useLoad(async () => {
    try { return unwrap(await api.GET('/api/jobs/{job_id}', { params: { path: { job_id: id } } })) }
    catch (e) { if (e instanceof ApiError && e.status === 404) return null; throw e }
  }, [id])
  const stream = useRunStream(runId, () => q.reload())

  async function analyse() {
    const r = unwrap(await api.POST('/api/jobs/{job_id}/analyze', { params: { path: { job_id: id } } }))
    setRunId(r.run_id)
  }

  if (q.loading) return <Loading />
  if (q.error) return <ErrorState message={q.error} onRetry={q.reload} />
  const d = q.data
  if (!d) return (
    <div>
      <PageHeader title={id} subtitle="Not analysed yet." actions={<button className="btn-primary" onClick={analyse}>Analyse now</button>} />
      {runId && <RunTimeline events={stream.events} status={stream.status} />}
    </div>
  )
  const job = d.job as Record<string, unknown>
  const spec = (d.job_spec ?? {}) as Record<string, unknown>
  const risk = (d.risk ?? {}) as Record<string, unknown>
  const fit = (d.fit ?? {}) as { score?: number; matrix?: Row[]; reasons?: string[] }
  const price = (d.price ?? {}) as Record<string, unknown>
  const dec = (d.decision ?? {}) as { action?: string; reasons?: string[] }

  return (
    <div className="space-y-5">
      <PageHeader title={String(job.title)} subtitle={<span className="flex flex-wrap items-center gap-2">
        <StatusChip status={d.status} /><ActionBadge action={dec.action} />
        <RiskBadge risk={risk.score as number} scam={risk.scam as boolean} injection={risk.injection_detected as boolean} />
      </span>} actions={<>
        {d.has_pending_approval && <Link className="btn-primary" to={`/studio/${id}`}>Open proposal studio</Link>}
        <button className="btn-ghost" onClick={analyse}>Re-run analysis</button>
      </>} />
      {d.attention && <p role="alert" className="card border-amber-300 bg-amber-50 p-3 text-sm">Needs attention: {d.attention}</p>}
      {runId && <section aria-label="Live run"><h2 className="mb-2 font-semibold">Live run</h2><RunTimeline events={stream.events} status={stream.status} /></section>}

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="card p-4 lg:col-span-2" aria-labelledby="bid-h">
          <h2 id="bid-h" className="font-semibold">Bid or skip — reasoning</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{(dec.reasons ?? []).map((r, i) => <li key={i}>{r}</li>)}</ul>
        </section>
        <section className="card p-4" aria-labelledby="price-h">
          <h2 id="price-h" className="font-semibold">Price</h2>
          {price.amount ? <>
            <p className="mt-1 text-2xl font-bold">${Number(price.amount).toLocaleString()}{price.bid_type === 'hourly' ? '/h' : ''}</p>
            <p className="text-xs text-muted">Fair band ${Number(price.band_low).toLocaleString()}–${Number(price.band_high).toLocaleString()}</p>
            <p className="mt-2 text-sm">{String(price.rationale ?? '')}</p>
          </> : <p className="mt-1 text-sm text-muted">Priced only when GigBid recommends bidding.</p>}
        </section>
      </div>

      <section className="card p-4" aria-labelledby="matrix-h">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="matrix-h" className="font-semibold">Requirement → evidence matrix</h2><FitBar fit={fit.score} />
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="text-xs uppercase text-muted"><tr><th className="py-2 pr-3">Requirement</th><th className="pr-3">Status</th><th>Portfolio items that prove it</th></tr></thead>
            <tbody>
              {(fit.matrix ?? []).map((r, i) => (
                <tr key={i} className="border-t border-line align-top">
                  <td className="py-2 pr-3">{r.requirement}</td>
                  <td className="pr-3"><span className={`chip ${r.status === 'supported' ? 'bg-emerald-100 text-emerald-800' : r.status === 'weak' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'}`}>{r.status}</span></td>
                  <td className="py-2">{r.evidence.length ? r.evidence.map((e) => (
                    <div key={e.evidence_id} className="mb-1"><strong>{e.project}</strong> <span className="text-muted">· {e.type}</span>
                      <div className="text-xs text-muted">{(e.snippet ?? '').slice(0, 140)}…</div></div>)) : <span className="text-muted">No evidence — will not be claimed</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card p-4" aria-labelledby="spec-h">
          <h2 id="spec-h" className="font-semibold">JobSpec <span className="text-xs text-muted">({String(spec.source ?? '')})</span></h2>
          <dl className="mt-2 grid grid-cols-3 gap-2 text-sm">
            <dt className="text-muted">Skills</dt><dd className="col-span-2">{((spec.skills as string[]) ?? []).join(', ') || '—'}</dd>
            <dt className="text-muted">Effort</dt><dd className="col-span-2">{String(spec.est_hours ?? '—')} h · {String(spec.complexity ?? '')}</dd>
            <dt className="text-muted">Deliverables</dt><dd className="col-span-2">{((spec.deliverables as string[]) ?? []).join('; ') || '—'}</dd>
            <dt className="text-muted">Hidden needs</dt><dd className="col-span-2">{((spec.hidden_needs as string[]) ?? []).join('; ') || '—'}</dd>
            <dt className="text-muted">Screening</dt><dd className="col-span-2">{((spec.screening_questions as string[]) ?? []).join(' · ') || '—'}</dd>
          </dl>
        </section>
        <section className="card p-4" aria-labelledby="risk-h">
          <h2 id="risk-h" className="font-semibold">Risk report</h2>
          <p className="mt-1 text-sm">Score <strong>{Number(risk.score ?? 0).toFixed(2)}</strong> · client quality {Number(risk.client_quality ?? 0).toFixed(2)}</p>
          <div className="mt-2 flex flex-wrap gap-1">{((risk.flags as string[]) ?? []).map((f) => <span key={f} className="chip bg-slate-100">{f}</span>)}</div>
          <p className="mt-2 text-sm text-muted">{String(risk.explanation ?? '')}</p>
          {((risk.injected_spans as string[]) ?? []).length > 0 && (
            <div className="mt-2 rounded bg-purple-50 p-2 text-xs"><strong>Ignored instruction-like text:</strong>
              <ul className="list-disc pl-4">{(risk.injected_spans as string[]).map((s, i) => <li key={i}><q>{s}</q></li>)}</ul></div>)}
        </section>
      </div>

      <details className="card p-4">
        <summary className="cursor-pointer font-semibold">Original job post (untrusted)</summary>
        <pre className="mt-2 whitespace-pre-wrap text-sm">{String(job.description)}</pre>
      </details>
      <p className="text-sm"><Link className="text-brand underline" to={`/runs?job=${id}`}>See agent runs and checkpoint history for this job</Link></p>
    </div>
  )
}
