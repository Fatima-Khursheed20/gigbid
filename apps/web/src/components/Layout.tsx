import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { DegradedBanner } from './DegradedBanner'

const NAV = [
  ['/inbox', 'Inbox'], ['/pipeline', 'Pipeline'], ['/messages', 'Messages'], ['/runs', 'Agent runs'],
  ['/analytics', 'Analytics'], ['/settings', 'Settings'],
] as const

export function Layout() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  return (
    <div className="min-h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:p-2">Skip to content</a>
      <header className="sticky top-0 z-30 border-b border-line bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <NavLink to="/inbox" className="flex items-center gap-2 font-bold">
            <span aria-hidden className="grid h-7 w-7 place-items-center rounded-lg bg-brand text-sm text-white">G</span> GigBid
          </NavLink>
          <nav aria-label="Main" className="hidden flex-1 gap-1 md:flex">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} className={({ isActive }) => `rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-indigo-50 font-semibold text-brand' : 'text-slate-600 hover:bg-slate-100'}`}>{label}</NavLink>
            ))}
          </nav>
          <div className="ml-auto hidden items-center gap-3 text-sm md:flex">
            <span className="text-muted" title={user?.email}>{user?.name}{user?.persona ? ` · ${user.persona}` : ''}</span>
            <button className="btn-ghost" onClick={async () => { await logout(); nav('/login') }}>Sign out</button>
          </div>
          <button className="btn-ghost ml-auto md:hidden" aria-expanded={open} aria-controls="mobile-nav" onClick={() => setOpen(!open)}>Menu</button>
        </div>
        {open && (
          <nav id="mobile-nav" aria-label="Main mobile" className="border-t border-line px-4 py-2 md:hidden">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} onClick={() => setOpen(false)} className="block rounded px-2 py-2 text-sm">{label}</NavLink>
            ))}
            <button className="btn-ghost mt-2 w-full" onClick={async () => { await logout(); nav('/login') }}>Sign out</button>
          </nav>
        )}
      </header>
      <DegradedBanner />
      <main id="main" className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
