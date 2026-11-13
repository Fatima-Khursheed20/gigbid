import type { RunEvent } from '../lib/hooks'

const LABEL: Record<string, string> = {
  scout: 'Scout', analyst: 'Job Analyst', risk_assessor: 'Risk Assessor', fit_matcher: 'Fit Matcher', decide: 'Decision',
  pricing: 'Pricing Strategist', writer: 'Proposal Writer', verifier: 'Claim verification', critic: 'Critic', revise: 'Revision',
  compliance: 'Compliance Guard', prepare_preview: 'Dry-run preview', human_approval: 'Waiting for your approval',
  apply_edit: 'Applying your edit', submit: 'Submitting', load_thread: 'Reading messages', classify: 'Intent',
  find_slots: 'Calendar slots', draft_reply: 'Client Liaison', msg_compliance: 'Compliance Guard', msg_approval: 'Waiting for your approval',
  msg_send: 'Sending', msg_apply_edit: 'Applying your edit',
}

/** Node-by-node progress of a LangGraph run (live via SSE, or replayed from the stored trace). */
export function RunTimeline({ events, status }: { events: RunEvent[]; status?: string }) {
  const nodes: { node: string; state: 'running' | 'done' | 'error'; ev?: RunEvent; tools: RunEvent[] }[] = []
  for (const e of events) {
    if (e.kind === 'node_start' && e.node) nodes.push({ node: e.node, state: 'running', tools: [] })
    const cur = [...nodes].reverse().find((n) => n.node === e.node && n.state === 'running')
    if (e.kind === 'node_end' && cur) {
      cur.state = ['dead_letter', 'degraded'].includes(String(e.status)) ? 'error' : 'done'
      cur.ev = e
    }
    if ((e.kind === 'tool_call' || e.kind === 'tool_error' || e.kind === 'tool_unreachable') && cur) cur.tools.push(e)
  }
  return (
    <ol className="space-y-2" aria-live="polite" data-testid="run-timeline">
      {nodes.map((n, i) => (
        <li key={i} className="card flex flex-wrap items-start gap-3 p-3">
          <span aria-hidden className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${n.state === 'done' ? 'bg-ok' : n.state === 'error' ? 'bg-bad' : 'animate-pulse bg-brand'}`} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{LABEL[n.node] ?? n.node}</span>
              {n.ev && <span className="text-xs text-muted tabular-nums">{n.ev.latency_s}s · {n.ev.tokens ?? 0} tok · ${(n.ev.usd ?? 0).toFixed(5)}</span>}
              {n.ev?.models && n.ev.models.length > 0 && <span className="chip bg-slate-100 text-slate-600">{n.ev.models.join(', ')}</span>}
              {n.state === 'running' && <span className="text-xs text-brand">running…</span>}
            </div>
            {n.tools.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-xs text-muted">
                {n.tools.map((t, j) => (
                  <li key={j} className="truncate">
                    <code className="text-slate-700">{String(t.tool)}</code>{' '}
                    {t.kind === 'tool_call' ? `✓ ${t.ms ?? ''}ms` : `✗ ${String(t.error ?? 'unreachable').slice(0, 80)}`}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </li>
      ))}
      {status && !['streaming', 'connecting'].includes(status) && (
        <li className="text-sm text-muted">Run finished: <strong>{status.replaceAll('_', ' ')}</strong></li>
      )}
    </ol>
  )
}
