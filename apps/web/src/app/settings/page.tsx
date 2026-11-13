import { useState } from 'react'
import { ErrorState, Loading, PageHeader } from '../../components/States'
import { api, unwrap, type SavedSearch } from '../../lib/api/client'
import { useAuth } from '../../lib/auth'
import { useLoad } from '../../lib/hooks'

export default function SettingsPage() {
  const { user, refresh } = useAuth()
  const [msg, setMsg] = useState<string | null>(null)
  const searches = useLoad(async () => unwrap(await api.GET('/api/searches')), [])
  const memory = useLoad(async () => unwrap(await api.GET('/api/memory')), [])
  const [ns, setNs] = useState({ name: '', query: '', category: '' as '' | 'ai_ml' | 'web' | 'data' | 'other', interval_minutes: 30 })
  const [budget, setBudget] = useState({ weekly_connects_budget: user?.weekly_connects_budget ?? 80, floor_rate: user?.floor_rate ?? 20 })

  async function save(body: Record<string, unknown>) {
    unwrap(await api.PUT('/api/profile', { body }))
    await refresh(); setMsg('Saved.')
  }
  async function connectUpwork() {
    try {
      const r = await api.GET('/api/auth/upwork/start')
      if (r.data) window.location.href = (r.data as { authorization_url: string }).authorization_url
      else setMsg('Could not start Upwork OAuth (server unreachable or not configured).')
    } catch { setMsg('Could not start Upwork OAuth.') }
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" />
      {msg && <p role="status" className="text-sm text-ok">{msg}</p>}
      <div className="grid gap-4 md:grid-cols-2">
        <section className="card space-y-3 p-4" aria-labelledby="auto-h">
          <h2 id="auto-h" className="font-semibold">Autonomy</h2>
          <fieldset className="space-y-2 text-sm">
            <legend className="sr-only">Autonomy level</legend>
            {[['suggest', 'Suggest only — I review every recommendation'], ['auto_skip_low_fit', 'Auto-skip low-fit jobs (never auto-send)']].map(([v, l]) => (
              <label key={v} className="flex items-center gap-2"><input type="radio" name="autonomy" checked={user?.autonomy === v} onChange={() => save({ autonomy: v })} />{l}</label>
            ))}
          </fieldset>
          <p className="text-xs text-muted">GigBid never sends a proposal or message, or spends Connects, without your approval — at any autonomy level.</p>
        </section>
        <section className="card space-y-3 p-4" aria-labelledby="bud-h">
          <h2 id="bud-h" className="font-semibold">Budgets</h2>
          <div className="grid grid-cols-2 gap-2">
            <div><label className="label" htmlFor="wcb">Weekly Connects</label><input id="wcb" type="number" className="input" value={budget.weekly_connects_budget} onChange={(e) => setBudget({ ...budget, weekly_connects_budget: Number(e.target.value) })} /></div>
            <div><label className="label" htmlFor="fr">Floor $/h</label><input id="fr" type="number" className="input" value={budget.floor_rate} onChange={(e) => setBudget({ ...budget, floor_rate: Number(e.target.value) })} /></div>
          </div>
          <button className="btn-primary" onClick={() => save(budget)}>Save budgets</button>
        </section>
        <section className="card space-y-3 p-4" aria-labelledby="acc-h">
          <h2 id="acc-h" className="font-semibold">Connected accounts</h2>
          <p className="text-sm">Marketplace mode: <strong>{user?.marketplace_mode}</strong> · connected: {user?.connected.join(', ') || 'GigSim demo account'}</p>
          <button className="btn-ghost" onClick={connectUpwork}>Connect Upwork (OAuth 2.1)</button>
          <p className="text-xs text-muted">Live mode uses Upwork’s official MCP server only — no scraping, no browser automation. Drafts you approve here still need confirming on Upwork.</p>
        </section>
        <section className="card space-y-3 p-4" aria-labelledby="ss-h">
          <h2 id="ss-h" className="font-semibold">Saved searches</h2>
          {searches.loading ? <Loading /> : searches.error ? <ErrorState message={searches.error} /> : (
            <ul className="space-y-1 text-sm">{(searches.data ?? []).map((s: SavedSearch) => (
              <li key={s.id} className="flex items-center justify-between gap-2"><span>{s.name} <span className="text-muted">({s.category || 'any'} · every {s.interval_minutes}m)</span></span>
                <button className="btn-ghost text-xs" onClick={async () => { await api.DELETE('/api/searches/{search_id}', { params: { path: { search_id: s.id } } }); searches.reload() }}>Delete</button></li>))}</ul>)}
          <form className="grid grid-cols-2 gap-2" onSubmit={async (e) => { e.preventDefault(); unwrap(await api.POST('/api/searches', { body: { ...ns, pool: '' } })); setNs({ ...ns, name: '', query: '' }); searches.reload() }}>
            <input className="input col-span-2" placeholder="Name" aria-label="Search name" value={ns.name} onChange={(e) => setNs({ ...ns, name: e.target.value })} required />
            <input className="input" placeholder="Keywords" aria-label="Keywords" value={ns.query} onChange={(e) => setNs({ ...ns, query: e.target.value })} />
            <select className="input" aria-label="Category" value={ns.category} onChange={(e) => setNs({ ...ns, category: e.target.value as typeof ns.category })}>
              <option value="">Any</option><option value="ai_ml">AI/ML</option><option value="web">Web</option><option value="data">Data</option></select>
            <button className="btn-primary col-span-2">Add saved search</button>
          </form>
        </section>
      </div>
      <section className="card p-4" aria-labelledby="mem-h">
        <h2 id="mem-h" className="font-semibold">What GigBid has learned</h2>
        <p className="text-xs text-muted">Only promoted knowledge: a style rule needs ≥3 of your edits across ≥2 jobs; outcome stats need ≥3 real outcomes. Delete anything you disagree with.</p>
        {memory.loading ? <Loading /> : memory.error ? <ErrorState message={memory.error} /> : (
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            {(['style', 'outcome'] as const).map((k) => (
              <div key={k}><h3 className="label">{k === 'style' ? 'Style memory' : 'Outcome memory'}</h3>
                {(memory.data?.[k] ?? []).length === 0 ? <p className="text-sm text-muted">Nothing learned yet.</p> : (
                  <ul className="space-y-1 text-sm" data-testid={`memory-${k}`}>{(memory.data?.[k] ?? []).map((m) => (
                    <li key={String(m.key)} className="flex items-start justify-between gap-2"><span>{String(m.rule ?? `${m.category}: ${m.replied}/${m.submitted} replies`)}</span>
                      <button className="btn-ghost text-xs" onClick={async () => { await api.DELETE('/api/memory/{kind}/{key}', { params: { path: { kind: k, key: String(m.key) } } }); memory.reload() }}>Delete</button></li>))}</ul>)}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
