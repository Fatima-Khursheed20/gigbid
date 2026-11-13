import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../../components/States'
import { api, unwrap } from '../../lib/api/client'
import { useAuth } from '../../lib/auth'

const PERSONAS = [
  { id: 'ai_ml', title: 'AI/ML engineer', blurb: 'RAG, LLM agents, computer vision (16 projects)' },
  { id: 'fullstack', title: 'Full-stack web developer', blurb: 'React/Next.js, Node, Postgres, Stripe (15 projects)' },
  { id: 'data_analyst', title: 'Data analyst', blurb: 'SQL, dbt, Power BI, experiments (15 projects)' },
  { id: 'own', title: 'My own profile', blurb: 'Upload your CV, case studies and past proposals' },
] as const

export default function OnboardingPage() {
  const { user, refresh } = useAuth()
  const nav = useNavigate()
  const [step, setStep] = useState(1)
  const [persona, setPersona] = useState<string>(user?.persona ?? 'ai_ml')
  const [files, setFiles] = useState<FileList | null>(null)
  const [rates, setRates] = useState({ hourly_rate: 45, floor_rate: 30, min_project: 300, weekly_connects_budget: 80 })
  const [gsToken, setGsToken] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(fn: () => Promise<void>) {
    setBusy(true); setErr(null)
    try { await fn() } catch (e) { setErr(e instanceof Error ? e.message : String(e)) } finally { setBusy(false) }
  }

  const savePersona = () => run(async () => {
    unwrap(await api.PUT('/api/profile', { body: { persona: persona as 'ai_ml' } }))
    if (persona === 'own' && files?.length) {
      const fd = new FormData()
      Array.from(files).forEach((f) => fd.append('files', f))
      const r = await fetch('/api/portfolio/upload', { method: 'POST', body: fd, credentials: 'include',
        headers: localStorage.getItem('gigbid_token') ? { Authorization: `Bearer ${localStorage.getItem('gigbid_token')}` } : {} })
      if (!r.ok) throw new Error(`upload failed: ${r.status}`)
    }
    setStep(2)
  })
  const saveRates = () => run(async () => {
    unwrap(await api.PUT('/api/profile', { body: rates }))
    setStep(3)
  })
  const finish = () => run(async () => {
    if (gsToken) unwrap(await api.POST('/api/accounts/connect', { body: { provider: 'gigsim', token: gsToken } }))
    const cat = persona === 'fullstack' ? 'web' : persona === 'data_analyst' ? 'data' : 'ai_ml'
    unwrap(await api.POST('/api/searches', { body: { name: 'New jobs in my category', category: cat as 'web', pool: 'stream', interval_minutes: 30, query: '' } }))
    unwrap(await api.PUT('/api/profile', { body: { onboarded: true } }))
    await refresh()
    nav('/inbox')
  })

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <PageHeader title="Set up GigBid" subtitle={`Step ${step} of 3`} />
      {err && <p role="alert" className="mb-3 text-sm text-bad">{err}</p>}
      {step === 1 && (
        <section className="card space-y-4 p-5" aria-labelledby="s1">
          <h2 id="s1" className="font-semibold">1. Whose portfolio should GigBid use?</h2>
          <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Portfolio">
            {PERSONAS.map((p) => (
              <label key={p.id} className={`card cursor-pointer p-3 ${persona === p.id ? 'ring-2 ring-brand' : ''}`}>
                <input type="radio" name="persona" value={p.id} className="sr-only" checked={persona === p.id} onChange={() => setPersona(p.id)} />
                <span className="block font-medium">{p.title}</span><span className="text-xs text-muted">{p.blurb}</span>
              </label>
            ))}
          </div>
          {persona === 'own' && (
            <div><label className="label" htmlFor="files">Upload CV (PDF), case studies (.md) or proposals (.jsonl)</label>
              <input id="files" type="file" multiple accept=".pdf,.md,.txt,.jsonl" onChange={(e) => setFiles(e.target.files)} className="input" /></div>
          )}
          <button className="btn-primary" disabled={busy} onClick={savePersona} data-testid="onboard-next-1">Continue</button>
        </section>
      )}
      {step === 2 && (
        <section className="card space-y-4 p-5" aria-labelledby="s2">
          <h2 id="s2" className="font-semibold">2. Rates and budget</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {([['hourly_rate', 'Target hourly rate ($)'], ['floor_rate', 'Never below ($/h)'], ['min_project', 'Minimum project ($)'],
              ['weekly_connects_budget', 'Weekly Connects budget']] as const).map(([k, l]) => (
              <div key={k}><label className="label" htmlFor={k}>{l}</label>
                <input id={k} type="number" min={0} className="input" value={rates[k]} onChange={(e) => setRates({ ...rates, [k]: Number(e.target.value) })} /></div>
            ))}
          </div>
          <button className="btn-primary" disabled={busy} onClick={saveRates} data-testid="onboard-next-2">Continue</button>
        </section>
      )}
      {step === 3 && (
        <section className="card space-y-4 p-5" aria-labelledby="s3">
          <h2 id="s3" className="font-semibold">3. Connect a marketplace</h2>
          <p className="text-sm text-muted">GigSim (simulator) works out of the box. Live Upwork uses the official Upwork MCP server with OAuth — you can connect it later in Settings.</p>
          <div><label className="label" htmlFor="gs">GigSim account token (optional)</label>
            <input id="gs" className="input" placeholder="gs-yourname (leave empty for a fresh demo account)" value={gsToken} onChange={(e) => setGsToken(e.target.value)} /></div>
          <p className="text-xs text-muted">We'll add a saved search for new jobs in your category, checked every 30 minutes.</p>
          <button className="btn-primary" disabled={busy} onClick={finish} data-testid="onboard-finish">Finish and open inbox</button>
        </section>
      )}
    </div>
  )
}
