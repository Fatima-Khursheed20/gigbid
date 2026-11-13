import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, setToken, unwrap, type Me } from './api/client'

type Auth = {
  user: Me | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, name: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const Ctx = createContext<Auth | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    const res = await api.GET('/api/auth/me')
    setUser(res.data ?? null)
  }, [])

  useEffect(() => { refresh().finally(() => setLoading(false)) }, [refresh])

  const login = async (email: string, password: string) => {
    const out = unwrap(await api.POST('/api/auth/login', { body: { email, password } }))
    setToken(out.token)
    setUser(out.user)
  }
  const register = async (email: string, password: string, name: string) => {
    const out = unwrap(await api.POST('/api/auth/register', { body: { email, password, name } }))
    setToken(out.token)
    setUser(out.user)
  }
  const logout = async () => {
    await api.POST('/api/auth/logout')
    setToken(null)
    setUser(null)
  }
  return <Ctx.Provider value={{ user, loading, login, register, logout, refresh }}>{children}</Ctx.Provider>
}

export function useAuth(): Auth {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth outside AuthProvider')
  return v
}
