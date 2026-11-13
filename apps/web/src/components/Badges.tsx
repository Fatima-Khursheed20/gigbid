export function RiskBadge({ risk, scam, injection }: { risk?: number | null; scam?: boolean | null; injection?: boolean | null }) {
  if (scam) return <span className="chip bg-red-100 text-red-800" title="Likely scam">⛔ Scam risk</span>
  const r = risk ?? 0
  return (
    <span className="inline-flex flex-wrap gap-1">
      {r >= 0.4
        ? <span className="chip bg-amber-100 text-amber-800" title={`Risk ${r.toFixed(2)}`}>⚠ Risk {r.toFixed(2)}</span>
        : <span className="chip bg-emerald-100 text-emerald-800" title={`Risk ${r.toFixed(2)}`}>✓ Low risk</span>}
      {injection && <span className="chip bg-purple-100 text-purple-800" title="Instruction-like text aimed at AI tools was found and ignored">🛡 Injection ignored</span>}
    </span>
  )
}

export function ActionBadge({ action }: { action?: string | null }) {
  const map: Record<string, string> = {
    bid: 'bg-indigo-100 text-indigo-800', watch: 'bg-slate-200 text-slate-800', skip: 'bg-slate-100 text-slate-500',
  }
  if (!action) return <span className="chip bg-slate-100 text-slate-500">pending</span>
  return <span className={`chip ${map[action] ?? 'bg-slate-100'}`}>{action === 'bid' ? 'Recommend bid' : action === 'skip' ? 'Recommend skip' : 'Watch'}</span>
}

export function FitBar({ fit }: { fit?: number | null }) {
  const v = Math.round((fit ?? 0) * 100)
  return (
    <div className="flex items-center gap-2" aria-label={`Fit ${v}%`}>
      <div className="h-2 w-20 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full ${v >= 55 ? 'bg-ok' : v >= 35 ? 'bg-warn' : 'bg-slate-400'}`} style={{ width: `${v}%` }} />
      </div>
      <span className="text-xs tabular-nums text-muted">{fit == null ? '—' : `${v}%`}</span>
    </div>
  )
}

export function StatusChip({ status }: { status?: string | null }) {
  const s = status ?? 'unknown'
  const tone = ['submitted', 'sent', 'hired'].includes(s) ? 'bg-emerald-100 text-emerald-800'
    : ['awaiting_approval'].includes(s) ? 'bg-indigo-100 text-indigo-800'
      : ['degraded', 'dead_letter', 'needs_attention', 'blocked', 'failed'].includes(s) ? 'bg-red-100 text-red-800'
        : 'bg-slate-100 text-slate-700'
  return <span className={`chip ${tone}`}>{s.replaceAll('_', ' ')}</span>
}
