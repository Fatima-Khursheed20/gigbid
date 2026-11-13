import { useState } from 'react'
import { ApprovalPanel, type Preview } from '../../components/ApprovalPanel'
import { RunTimeline } from '../../components/RunTimeline'
import { Empty, ErrorState, Loading, PageHeader } from '../../components/States'
import { api, unwrap, type Thread } from '../../lib/api/client'
import { useLoad, useRunStream } from '../../lib/hooks'

type Msg = { id: number; sender: string; body: string; intent?: string }
type Payload = { intent?: { intent: string; injection_detected?: boolean; summary?: string }; reply: { body: string; proposed_slots?: { start: string }[] }; preview?: Preview }

function ThreadView({ id }: { id: string }) {
  const q = useLoad(async () => unwrap(await api.GET('/api/messages/threads/{thread_id}', { params: { path: { thread_id: id } } })), [id])
  const [runId, setRunId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [edit, setEdit] = useState<string | null>(null)
  const stream = useRunStream(runId, () => { setBusy(false); q.reload() })

  async function draft() {
    setBusy(true)
    const r = unwrap(await api.POST('/api/messages/threads/{thread_id}/draft', { params: { path: { thread_id: id } } }))
    setRunId(r.run_id)
  }
  async function decide(action: 'approve' | 'edit' | 'reject', extra: { edited_text?: string; reason?: string } = {}) {
    setBusy(true)
    const r = unwrap(await api.POST('/api/messages/threads/{thread_id}/decision', { params: { path: { thread_id: id } }, body: { action, ...extra } }))
    setRunId(r.run_id)
    setEdit(null)
  }
  if (q.loading) return <Loading />
  if (q.error) return <ErrorState message={q.error} onRetry={q.reload} />
  const msgs = (q.data?.messages ?? []) as Msg[]
  const p = q.data?.payload as Payload | undefined
  return (
    <div className="space-y-4">
      <ol className="space-y-2" aria-label="Messages">
        {msgs.map((m) => (
          <li key={m.id} className={`max-w-[85%] rounded-xl p-3 text-sm ${m.sender === 'client' ? 'bg-white border border-line' : 'ml-auto bg-indigo-50'}`}>
            <p className="mb-1 text-xs font-semibold text-muted">{m.sender}{m.intent ? ` · ${m.intent}` : ''}</p>{m.body}
          </li>
        ))}
      </ol>
      {runId && <RunTimeline events={stream.events} status={stream.status} />}
      {p ? (
        <div className="grid gap-4 md:grid-cols-2">
          <section className="card p-4" aria-labelledby="reply-h">
            <h3 id="reply-h" className="font-semibold">Suggested reply <span className="chip bg-slate-100">{p.intent?.intent}</span>
              {p.intent?.injection_detected && <span className="chip ml-1 bg-purple-100 text-purple-800">🛡 injection ignored</span>}</h3>
            {edit === null ? <p className="mt-2 whitespace-pre-wrap text-sm">{p.reply.body}</p>
              : <textarea aria-label="Edit reply" className="input mt-2 min-h-40" value={edit} onChange={(e) => setEdit(e.target.value)} />}
            {p.reply.proposed_slots && p.reply.proposed_slots.length > 0 && (
              <p className="mt-2 text-xs text-muted">Interview slots (tentative holds created on approval): {p.reply.proposed_slots.map((s) => s.start.slice(0, 16).replace('T', ' ')).join(' · ')}</p>)}
            <div className="mt-3 flex gap-2">
              {edit === null ? <button className="btn-ghost" onClick={() => setEdit(p.reply.body)}>Edit</button>
                : <button className="btn-primary" disabled={busy} onClick={() => decide('edit', { edited_text: edit })}>Save & re-check</button>}
            </div>
          </section>
          <ApprovalPanel kind="message" preview={p.preview} busy={busy} editing={edit !== null} onApprove={() => decide('approve')} onReject={(reason) => decide('reject', { reason })} />
        </div>
      ) : (
        <button className="btn-primary" disabled={busy} onClick={draft}>Suggest a reply</button>
      )}
    </div>
  )
}

export default function MessagesPage() {
  const q = useLoad(async () => unwrap(await api.GET('/api/messages/threads')), [], 15000)
  const [sel, setSel] = useState<string | null>(null)
  return (
    <div>
      <PageHeader title="Messages" subtitle="Client replies with suggested responses and interview slots. Nothing is sent until you approve." />
      {q.loading && <Loading />}
      {q.error && <ErrorState message={q.error} onRetry={q.reload} />}
      {!q.loading && !q.error && (q.data ?? []).length === 0 && <Empty title="No client conversations yet">When a client replies to a submitted proposal it shows up here.</Empty>}
      <div className="grid gap-4 md:grid-cols-3">
        <ul className="space-y-2" aria-label="Threads">
          {(q.data ?? []).map((t: Thread) => (
            <li key={t.thread_id}>
              <button className={`card w-full p-3 text-left text-sm ${sel === t.thread_id ? 'ring-2 ring-brand' : ''}`} onClick={() => setSel(t.thread_id)}>
                <span className="block font-medium">{t.job_id ?? t.thread_id}</span>
                <span className="block text-xs text-muted">{t.intent ?? 'new'} · {t.status ?? 'unread'} · {t.n} messages</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="md:col-span-2">{sel ? <ThreadView key={sel} id={sel} /> : (q.data ?? []).length > 0 && <Empty title="Pick a thread" />}</div>
      </div>
    </div>
  )
}
