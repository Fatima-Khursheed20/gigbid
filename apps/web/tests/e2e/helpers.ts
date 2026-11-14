import { expect, type APIRequestContext, type Page } from '@playwright/test'

export const uniq = () => `${Date.now()}${Math.floor(Math.random() * 1000)}`

/** Register a fresh user (isolated tenant state) and sign the browser in. */
export async function newUser(page: Page, persona: 'ai_ml' | 'fullstack' | 'data_analyst' = 'ai_ml') {
  const email = `e2e-${uniq()}@gigbid.test`
  const password = 'e2e-password-123'
  const r = await page.request.post('/api/auth/register', { data: { email, password, name: 'E2E Tester' } })
  expect(r.ok()).toBeTruthy()
  const { token } = await r.json()
  const auth = { Authorization: `Bearer ${token}` }
  await page.request.put('/api/profile', { data: { persona, onboarded: true }, headers: auth })
  await page.addInitScript((t) => localStorage.setItem('gigbid_token', t), token)
  return { email, password, token, auth }
}

/** Ask the worker to analyse a job and wait until a proposal is waiting for approval. */
export async function draftFor(request: APIRequestContext, auth: Record<string, string>, jobId: string) {
  const r = await request.post(`/api/jobs/${jobId}/analyze`, { headers: auth })
  expect(r.ok()).toBeTruthy()
  await expect.poll(async () => {
    const s = await request.get(`/api/proposals/${jobId}`, { headers: auth })
    return s.ok() ? (await s.json()).pending : false
  }, { timeout: 200_000, intervals: [2000] }).toBe(true)
}
