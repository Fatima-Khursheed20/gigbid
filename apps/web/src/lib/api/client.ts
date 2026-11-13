// Typed API client. Types in ./schema.d.ts are GENERATED from FastAPI's OpenAPI schema
// (npm run gen:api) — do not hand-edit them.
import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

export type Schemas = components['schemas']
export type Me = Schemas['Me']
export type InboxItem = Schemas['InboxItem']
export type JobDetail = Schemas['JobDetail']
export type Studio = Schemas['Studio']
export type Run = Schemas['Run']
export type RunDetail = Schemas['RunDetail']
export type PipelineCard = Schemas['PipelineCard']
export type Thread = Schemas['Thread']
export type ThreadDetail = Schemas['ThreadDetail']
export type Analytics = Schemas['Analytics']
export type Health = Schemas['Health']
export type SavedSearch = Schemas['SavedSearch']

const TOKEN_KEY = 'gigbid_token'

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null) {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ }
}

export const api = createClient<paths>({ baseUrl: '', credentials: 'include' })
api.use({
  onRequest({ request }) {
    const t = getToken()
    if (t) request.headers.set('Authorization', `Bearer ${t}`)
    return request
  },
})

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

/** Unwrap an openapi-fetch result or throw a readable error. */
export function unwrap<T>(res: { data?: T; error?: unknown; response: Response }): T {
  if (res.error !== undefined || res.data === undefined) {
    const e = res.error as { detail?: unknown } | undefined
    const detail = typeof e?.detail === 'string' ? e.detail : JSON.stringify(e?.detail ?? res.error ?? 'request failed')
    throw new ApiError(res.response.status, detail)
  }
  return res.data
}
