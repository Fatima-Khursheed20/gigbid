import { useState } from 'react'

export type Preview = {
  would_send?: { cover_letter?: string; screening_answers?: string[]; bid_amount?: number; bid_type?: string } | string
  connects_cost?: number | null
  balance_before?: number | null
  balance_after?: number | null
  marketplace?: string
  cost?: string
}

/** Approve / edit / reject. Shows the dry_run preview: exactly what will be sent and what it costs. */
export function ApprovalPanel({ preview, busy, onApprove, onReject, editing, kind = 'proposal' }: {
  preview?: Preview | null
  busy?: boolean
  onApprove: () => void
  onReject: (reason: string) => void
  editing?: boolean
  kind?: 'proposal' | 'message'
}) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const ws = preview?.would_send
  return (
    <section className="card p-4" aria-labelledby="approval-h">
      <h2 id="approval-h" className="font-semibold">Your approval</h2>
      <p className="mt-1 text-xs text-muted">Nothing is sent until you approve. {kind === 'proposal' && 'Approving submits the draft and spends Connects.'}</p>
      {preview && (
        <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm" data-testid="dry-run-preview">
          <p className="label">Dry-run preview ({preview.marketplace ?? 'marketplace'})</p>
          {typeof ws === 'object' && ws && (
            <ul className="space-y-1">
              <li>Bid: <strong>${ws.bid_amount?.toLocaleString()}{ws.bid_type === 'hourly' ? '/h' : ''}</strong> ({ws.bid_type})</li>
              <li>Screening answers: {ws.screening_answers?.length ?? 0}</li>
            </ul>
          )}
          {typeof ws === 'string' && <p className="whitespace-pre-wrap">{ws}</p>}
          {kind === 'proposal' ? (
            <p className="mt-2">Cost: <strong>{preview.connects_cost ?? '?'} Connects</strong> · balance {preview.balance_before ?? '?'} → <strong>{preview.balance_after ?? '?'}</strong></p>
          ) : <p className="mt-2">Cost: {preview.cost ?? 'free'}</p>}
        </div>
      )}
      {!rejecting ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn-primary" disabled={busy || editing} onClick={onApprove} data-testid="approve">
            {kind === 'proposal' ? 'Approve & submit' : 'Approve & send'}
          </button>
          <button className="btn-ghost" disabled={busy} onClick={() => setRejecting(true)} data-testid="reject">Reject…</button>
        </div>
      ) : (
        <form className="mt-4 space-y-2" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) onReject(reason.trim()) }}>
          <label className="label" htmlFor="reason">Why reject? (feeds analytics)</label>
          <select id="reason-preset" className="input" aria-label="Common reasons" onChange={(e) => setReason(e.target.value)} value={reason}>
            <option value="">Choose or type below…</option>
            <option>Too generic</option><option>Wrong price</option><option>Not interested in this client</option>
            <option>Claims I would not make</option><option>Bad timing</option>
          </select>
          <input id="reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason" data-testid="reject-reason" />
          <div className="flex gap-2">
            <button type="submit" className="btn-danger" disabled={busy || !reason.trim()} data-testid="confirm-reject">Reject</button>
            <button type="button" className="btn-ghost" onClick={() => setRejecting(false)}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  )
}
