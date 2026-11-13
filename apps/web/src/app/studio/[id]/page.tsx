import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApprovalPanel, type Preview } from '../../../components/ApprovalPanel'
import { StatusChip } from '../../../components/Badges'
import { EvidenceHover, type Claim, type Evidence } from '../../../components/EvidenceHover'
import { RunTimeline } from '../../../components/RunTimeline'
import { Empty, ErrorState, Loading, PageHeader } from '../../../components/States'
import { api, unwrap } from '../../../lib/api/client'
import { useLoad, useRunStream } from '../../../lib/hooks'

type Payload = {
  job: { title: string; job_id: string }
  draft: { cover_letter: string; screening_answers: { question: string; answer: string }[]; claims?: Claim[]; word_count?: number; version?: number }
  evidence: Evidence[]
  critiques?: { approve: boolean; issues: { kind: string; detail: string }[]; round: number; score?: number }[]
  compliance?: { ok: boolean; violations: { rule: string; excerpt: string; fix: string }[]; policy_version?: string }
  verification?: { before: { claims: number; unsupported: number }; after: { claims: number; unsupported: number } }
  price?: { amount: number; bid_type: string; rationale: string }
  risk?: { score: number; flags: string[] }
  preview?: Preview
}

const strip = (t: string) => t.replace(/\s?\[E\d+\]/g, '')

export default function StudioPage() {
  const { id = '' } = useParams()
  const q = useLoad(async () => unwrap(await api.GET('/api/proposals/{job_id}', { params: { path: { job_id: id } } })), [id])
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const [regenFrom, setRegenFrom] = useState<string | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const stream = useRunStream(runId, () => { setBusy(false); q.reload() })

  const p = q.data?.payload as Payload | undefined

  async function decide(action: 'approve' | 'edit' | 'reject', extra: { edited_text?: string; reason?: string } = {}) {
    setBusy(true); setErr(null)
    try {
      const r = unwrap(await api.POST('/api/proposals/{job_id}/decision', { params: { path: { job_id: id } }, body: { action, ...extra } }))
      setRunId(r.run_id)
      setEditing(false)
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); setBusy(false) }
  }

  async function regenerate(i: number) {
    setBusy(true); setErr(null)
    try {
      const r = unwrap(await api.POST('/api/proposals/{job_id}/regenerate', { params: { path: { job_id: id } }, body: { paragraph_index: i, instruction: '' } }))
      setText(strip(r.cover_letter)); setRegenFrom(strip(r.cover_letter)); setEditing(true)
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) } finally { setBusy(false) }
  }

  if (q.loading) return <Loading />
  if (q.error) return <ErrorState message={q.error} onRetry={q.reload} />
  if (!q.data?.pending || !p) {
    return (
      <div className="space-y-4">
        <PageHeader title="Proposal studio" subtitle={<>Status: <StatusChip status={q.data?.status} /></>} />
        {runId && <RunTimeline events={stream.events} status={stream.status} />}
        {q.data?.submission ? (
          <div className="card p-4 text-sm" data-testid="submitted">
            <p className="font-semibold">Submitted ✓</p>
            <p>Proposal {String((q.data.submission as Record<string, unknown>).proposal_id)} · {String((q.data.submission as Record<string, unknown>).connects_cost)} Connects spent.</p>
            <Link className="text-brand underline" to="/pipeline">View pipeline</Link>
          </div>
        ) : <Empty title="No draft waiting for approval">{q.data?.status === 'rejected' ? 'You rejected this draft.' : 'Analyse a job from the inbox to get a draft.'}</Empty>}
      </div>
    )
  }

  const paragraphs = p.draft.cover_letter.split(/\n\s*\n/).filter((x) => x.trim())
  const crit = p.critiques?.[p.critiques.length - 1]
  return (
    <div className="space-y-5">
      <PageHeader title={p.job.title} subtitle={<span>Draft v{p.draft.version} · {p.draft.word_count} words · <Link className="text-brand underline" to={`/jobs/${id}`}>job detail</Link></span>} />
      {err && <p role="alert" className="text-sm text-bad">{err}</p>}
      {runId && <RunTimeline events={stream.events} status={stream.status} />}
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <section className="card p-5" aria-labelledby="draft-h">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 id="draft-h" className="font-semibold">Cover letter</h2>
              {!editing
                ? <button className="btn-ghost" onClick={() => { setText(strip(p.draft.cover_letter)); setRegenFrom(null); setEditing(true) }} data-testid="edit">Edit</button>
                : <span className="text-xs text-muted">Edits are diffed, learned only through the style-memory rule, and re-checked by Compliance.</span>}
            </div>
            {!editing ? (
              <>
                <EvidenceHover text={p.draft.cover_letter} evidence={p.evidence} claims={p.draft.claims ?? []} />
                <p className="mt-3 text-xs text-muted">Hover or focus an underlined sentence to see the portfolio evidence behind it. Green = supported, amber = partly, red = unsupported.</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {paragraphs.map((_, i) => <button key={i} className="btn-ghost text-xs" disabled={busy} onClick={() => regenerate(i)}>↻ Regenerate paragraph {i + 1}</button>)}
                </div>
              </>
            ) : (
              <div className="space-y-2">
                <label className="label" htmlFor="draft-edit">Edit draft</label>
                <textarea id="draft-edit" className="input min-h-64 font-[inherit] leading-6" value={text} onChange={(e) => setText(e.target.value)} data-testid="draft-editor" />
                <div className="flex gap-2">
                  <button className="btn-primary" disabled={busy || !text.trim()} data-testid="save-edit"
                    onClick={() => decide('edit', { edited_text: text, reason: regenFrom !== null && text === regenFrom ? 'regenerate' : undefined })}>Save & re-check</button>
                  <button className="btn-ghost" onClick={() => setEditing(false)}>Cancel</button>
                </div>
              </div>
            )}
          </section>
          {p.draft.screening_answers.length > 0 && (
            <section className="card p-5" aria-labelledby="sa-h">
              <h2 id="sa-h" className="font-semibold">Screening answers</h2>
              {p.draft.screening_answers.map((a, i) => (
                <div key={i} className="mt-3"><p className="text-sm font-medium">{a.question}</p>
                  <EvidenceHover text={a.answer} evidence={p.evidence} claims={p.draft.claims ?? []} /></div>
              ))}
            </section>
          )}
        </div>
        <aside className="space-y-4">
          <ApprovalPanel preview={p.preview} busy={busy} editing={editing} onApprove={() => decide('approve')} onReject={(reason) => decide('reject', { reason })} />
          <section className="card p-4 text-sm" aria-labelledby="checks-h">
            <h2 id="checks-h" className="font-semibold">Checks</h2>
            {p.verification && <p className="mt-2">Claim verification: {p.verification.before.unsupported}/{p.verification.before.claims} unsupported before → <strong>{p.verification.after.unsupported}/{p.verification.after.claims}</strong> after</p>}
            {crit && (
              <div className="mt-2"><p className="font-medium">Critic (round {crit.round}) {crit.approve ? '✓ approved' : '— issues remained'}</p>
                <ul className="list-disc pl-5 text-muted">{crit.issues.map((x, i) => <li key={i}><strong>{x.kind}</strong>: {x.detail}</li>)}</ul></div>)}
            {p.compliance && (
              <div className="mt-2"><p className="font-medium">Compliance (policy {p.compliance.policy_version}) {p.compliance.ok ? '✓ clean' : 'fixed:'}</p>
                <ul className="list-disc pl-5 text-muted">{p.compliance.violations.map((v, i) => <li key={i}><strong>{v.rule}</strong>: “{v.excerpt}” → {v.fix}</li>)}</ul></div>)}
            {p.price && <p className="mt-2"><strong>Price rationale:</strong> {p.price.rationale}</p>}
          </section>
        </aside>
      </div>
    </div>
  )
}
