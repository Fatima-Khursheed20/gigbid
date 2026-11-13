import { api, type Health } from '../lib/api/client'
import { useLoad } from '../lib/hooks'

/** Shown whenever the marketplace (or another dependency) is unavailable: work is queued and retried. */
export function DegradedBanner() {
  const { data } = useLoad<Health | null>(async () => (await api.GET('/api/health')).data ?? null, [], 15000)
  if (!data || !data.degraded) return null
  const parts: string[] = []
  if (data.marketplace !== 'ok') parts.push(`Marketplace unavailable (${data.marketplace})`)
  if (data.portfolio !== 'ok') parts.push(`Portfolio search unavailable (${data.portfolio})`)
  if (data.db !== 'ok') parts.push(`Database ${data.db}`)
  return (
    <div role="alert" data-testid="degraded-banner" className="border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900">
      <strong>Degraded mode:</strong> {parts.join(' · ')}. New work is queued and will resume automatically; nothing is lost
      and nothing is sent without your approval.
    </div>
  )
}
