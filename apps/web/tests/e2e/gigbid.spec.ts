import { expect, test } from '@playwright/test'
import { draftFor, newUser, uniq } from './helpers'

// Jobs from the GigSim dev pool that the AI/ML persona should bid on (gold label bid=true).
const BID_JOBS = ['job-dev-ai-012', 'job-dev-ai-015', 'job-dev-ai-005']

test('onboarding: sign up, pick a persona, set rates, connect GigSim, land in the inbox @mobile', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: 'Create an account' }).click()
  await page.getByLabel('Name').fill('New Freelancer')
  await page.getByLabel('Email').fill(`onb-${uniq()}@gigbid.test`)
  await page.getByLabel('Password').fill('onboard-pass-123')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Set up GigBid' })).toBeVisible()
  await page.getByText('Data analyst', { exact: true }).click()
  await page.getByTestId('onboard-next-1').click()
  await page.getByLabel('Never below ($/h)').fill('18')
  await page.getByTestId('onboard-next-2').click()
  await page.getByLabel('GigSim account token (optional)').fill(`gs-e2e${uniq()}`)
  await page.getByTestId('onboard-finish').click()
  await expect(page.getByRole('heading', { name: 'Job inbox' })).toBeVisible()
  const me = await (await page.request.get('/api/auth/me')).json()
  expect(me.persona).toBe('data_analyst')
  expect(me.onboarded).toBe(true)
  expect(me.connected).toContain('gigsim')
})

test('approving a proposal submits it once and moves it to the pipeline', async ({ page }) => {
  const u = await newUser(page)
  await draftFor(page.request, u.auth, BID_JOBS[0])
  await page.goto(`/studio/${BID_JOBS[0]}`)
  await expect(page.getByTestId('dry-run-preview')).toContainText('Connects')
  await expect(page.getByTestId('evidence-draft')).toBeVisible()
  await page.getByTestId('approve').click()
  await expect(page.getByTestId('submitted')).toBeVisible({ timeout: 120_000 })
  await page.goto('/pipeline')
  await expect(page.getByTestId('kanban').getByRole('region', { name: 'submitted' })).toContainText(/\S/)
})

test('rejecting a proposal requires a reason and records it', async ({ page }) => {
  const u = await newUser(page)
  await draftFor(page.request, u.auth, BID_JOBS[1])
  await page.goto(`/studio/${BID_JOBS[1]}`)
  await page.getByTestId('reject').click()
  await expect(page.getByTestId('confirm-reject')).toBeDisabled()
  await page.getByTestId('reject-reason').fill('Too generic')
  await page.getByTestId('confirm-reject').click()
  await expect(page.getByText('You rejected this draft.')).toBeVisible({ timeout: 120_000 })
  const a = await (await page.request.get('/api/analytics', { headers: u.auth })).json()
  expect(a.rejection_reasons.map((r: { reason: string }) => r.reason)).toContain('Too generic')
})

test('editing a draft re-runs compliance and keeps the approval pending', async ({ page }) => {
  const u = await newUser(page)
  await draftFor(page.request, u.auth, BID_JOBS[2])
  await page.goto(`/studio/${BID_JOBS[2]}`)
  await page.getByTestId('edit').click()
  const edited = 'Your project needs a reliable model in production, which is the kind of system I deliver. ' +
    'In a similar engagement I set up retraining and drift detection so problems were caught within a day. ' +
    'Reach me on WhatsApp +1 555 010 9999 to discuss. I would begin by reviewing your data and agreeing on an ' +
    'evaluation set, then ship a first working version in week one and harden it with tests before handover.'
  await page.getByTestId('draft-editor').fill(edited)
  await page.getByTestId('save-edit').click()
  // the edit is re-checked by Compliance in the worker; wait for the new pending draft, then reload
  await expect.poll(async () => {
    const r = await (await page.request.get(`/api/proposals/${BID_JOBS[2]}`, { headers: u.auth })).json()
    return r.pending && r.history.length > 0
  }, { timeout: 200_000, intervals: [2000] }).toBe(true)
  await page.reload()
  await expect(page.getByTestId('approve')).toBeEnabled()
  const s = await (await page.request.get(`/api/proposals/${BID_JOBS[2]}`, { headers: u.auth })).json()
  expect(s.pending).toBe(true)
  expect(s.payload.draft.cover_letter).not.toMatch(/whatsapp/i) // compliance removed the off-platform contact
  expect(s.history.at(-1).action).toBe('edit')
})

test('degraded-mode banner appears when the marketplace is unavailable @mobile', async ({ page }) => {
  await newUser(page)
  await page.route('**/api/health', (route) => route.fulfill({
    json: { api: 'ok', db: 'ok', redis: 'ok', marketplace: 'down (ConnectError)', portfolio: 'ok', llm: 'ok',
      marketplace_mode: 'gigsim', model_profile: 'open', degraded: true },
  }))
  await page.goto('/inbox')
  await expect(page.getByTestId('degraded-banner')).toContainText('Marketplace unavailable')
  await expect(page.getByTestId('degraded-banner')).toContainText('queued')
})
