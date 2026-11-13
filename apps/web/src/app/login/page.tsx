import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'

export default function LoginPage() {
  const { login, register } = useAuth()
  const nav = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      if (mode === 'login') await login(email, password)
      else await register(email, password, name)
      nav(mode === 'login' ? '/inbox' : '/onboarding')
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : String(e2))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-full place-items-center bg-gradient-to-br from-indigo-50 to-white px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-brand text-xl font-bold text-white">G</div>
          <h1 className="text-2xl font-bold">GigBid</h1>
          <p className="mt-1 text-sm text-muted">Agents find, judge and draft. You approve every proposal and message.</p>
        </div>
        <form onSubmit={submit} className="card space-y-4 p-6" aria-label={mode === 'login' ? 'Sign in' : 'Create account'}>
          {mode === 'register' && (
            <div><label className="label" htmlFor="name">Name</label>
              <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} required /></div>
          )}
          <div><label className="label" htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="username" className="input" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
          <div><label className="label" htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={8}
              className="input" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
          {err && <p role="alert" className="text-sm text-bad">{err}</p>}
          <button className="btn-primary w-full" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
          <p className="text-center text-sm text-muted">
            {mode === 'login' ? 'New here?' : 'Have an account?'}{' '}
            <button type="button" className="font-medium text-brand underline" onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>
              {mode === 'login' ? 'Create an account' : 'Sign in'}
            </button>
          </p>
        </form>
        <p className="mt-4 text-center text-xs text-muted">Demo data is synthetic (GigSim marketplace simulator). No real clients are contacted.</p>
      </div>
    </div>
  )
}
