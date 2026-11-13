import { Fragment } from 'react'

export type Evidence = { evidence_id: string; project?: string | null; type?: string | null; text?: string; requirement?: string }
export type Claim = { claim: string; label: string; evidence_ids: string[]; action?: string }

const tone: Record<string, string> = {
  supported: 'decoration-emerald-500', partly_supported: 'decoration-amber-500', unsupported: 'decoration-red-500',
}

function splitSentences(t: string): string[] {
  return t.split(/(?<=[.!?])\s+|\n+/).filter((s) => s.trim())
}

/** Renders a draft so that every claim shows the portfolio evidence behind it on hover or keyboard focus. */
export function EvidenceHover({ text, evidence, claims }: { text: string; evidence: Evidence[]; claims: Claim[] }) {
  const paragraphs = text.split(/\n\s*\n/)
  return (
    <div className="space-y-3 text-[15px] leading-7" data-testid="evidence-draft">
      {paragraphs.map((p, pi) => (
        <p key={pi}>
          {splitSentences(p).map((s, si) => {
            const nums = [...s.matchAll(/\[E(\d+)\]/g)].map((m) => Number(m[1]))
            const clean = s.replace(/\s?\[E\d+\]/g, '')
            const ev = nums.map((n) => evidence[n - 1]).filter(Boolean)
            const claim = claims.find((c) => c.claim && (clean.includes(c.claim.replace(/\s?\[E\d+\]/g, '').slice(0, 40)) || c.claim.includes(clean.slice(0, 40))))
            const ids = claim?.evidence_ids ?? []
            const evAll = [...ev, ...evidence.filter((e) => ids.includes(e.evidence_id) && !ev.includes(e))]
            if (!evAll.length && !claim) return <Fragment key={si}>{clean} </Fragment>
            return (
              <span key={si} className="group relative">
                <span tabIndex={0} className={`cursor-help underline decoration-2 underline-offset-4 ${tone[claim?.label ?? 'supported']}`}
                  aria-describedby={`ev-${pi}-${si}`}>
                  {clean}
                </span>{' '}
                <span id={`ev-${pi}-${si}`} role="tooltip"
                  className="invisible absolute left-0 top-full z-20 mt-1 w-[min(28rem,85vw)] rounded-lg border border-line bg-white p-3 text-xs leading-5 text-ink opacity-0 shadow-lg transition group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100">
                  {claim && <span className="mb-1 block font-semibold">Claim check: {claim.label.replace('_', ' ')}</span>}
                  {evAll.length === 0 && <span className="block text-red-700">No portfolio evidence supports this sentence.</span>}
                  {evAll.map((e) => (
                    <span key={e.evidence_id} className="mb-2 block">
                      <span className="block font-medium">{e.project ?? 'Portfolio'} <span className="text-muted">· {e.type}</span></span>
                      <span className="block text-slate-600">{(e.text ?? '').slice(0, 260)}{(e.text ?? '').length > 260 ? '…' : ''}</span>
                      <span className="block text-[10px] text-muted">{e.evidence_id}</span>
                    </span>
                  ))}
                </span>
              </span>
            )
          })}
        </p>
      ))}
    </div>
  )
}
