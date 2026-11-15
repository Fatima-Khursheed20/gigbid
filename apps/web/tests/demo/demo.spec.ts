// Demo recording (not part of CI): npx playwright test -c tests/demo/demo.config.ts
// Walks: inbox → scam caught → injection ignored → job detail → proposal studio (evidence hover) → approve →
// pipeline → client reply handled → run viewer. Records video + numbered screenshots for the README GIF.
import { expect, test, type Page } from '@playwright/test'

const EMAIL = process.env.DEMO_EMAIL ?? ''
const PASSWORD = process.env.DEMO_PASSWORD ?? ''
const shot = async (page: Page, n: number, name: string) => {
  await page.waitForTimeout(900)
  await page.screenshot({ path: `../../docs/demo/frames/${String(n).padStart(2, '0')}-${name}.png` })
}

test('GigBid demo walkthrough', async ({ page }) => {
  test.setTimeout(30 * 60_000)
  await page.goto('/login')
  await page.getByLabel('Email').fill(EMAIL)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Job inbox' })).toBeVisible()
  await shot(page, 1, 'inbox')

  const jobs = await (await page.request.get('/api/jobs')).json()
  const scam = jobs.find((j: { scam: boolean }) => j.scam)
  const inj = jobs.find((j: { injection: boolean; scam: boolean }) => j.injection && !j.scam) ?? jobs.find((j: { injection: boolean }) => j.injection)
  const bid = jobs.find((j: { status: string }) => j.status === 'awaiting_approval')
  if (scam) { await page.goto(`/jobs/${scam.job_id}`); await shot(page, 2, 'scam-caught') }
  if (inj) {
    await page.goto(`/jobs/${inj.job_id}`)
    await page.getByText('Ignored instruction-like text').scrollIntoViewIfNeeded().catch(() => {})
    await shot(page, 3, 'injection-ignored')
  }
  expect(bid, 'a proposal awaiting approval').toBeTruthy()
  await page.goto(`/jobs/${bid.job_id}`)
  await shot(page, 4, 'job-detail-matrix')
  await page.getByText('Requirement → evidence matrix').scrollIntoViewIfNeeded()
  await shot(page, 5, 'evidence-matrix')
  await page.goto(`/studio/${bid.job_id}`)
  await expect(page.getByTestId('evidence-draft')).toBeVisible()
  const claim = page.locator('[data-testid="evidence-draft"] [tabindex="0"]').first()
  await claim.hover()
  await shot(page, 6, 'studio-evidence-hover')
  await page.getByTestId('approve').click()
  await expect(page.getByTestId('submitted')).toBeVisible({ timeout: 10 * 60_000 })
  await shot(page, 7, 'submitted')
  await page.goto('/pipeline')
  await shot(page, 8, 'pipeline')

  await page.goto('/messages')
  const thread = page.getByRole('list', { name: 'Threads' }).getByRole('button').first()
  if (await thread.isVisible().catch(() => false)) {
    await thread.click()
    const suggest = page.getByRole('button', { name: 'Suggest a reply' })
    if (await suggest.isVisible().catch(() => false)) await suggest.click()
    await expect(page.getByText('Suggested reply')).toBeVisible({ timeout: 10 * 60_000 })
    await shot(page, 9, 'reply-suggested')
    await page.getByTestId('approve').click()
    await page.waitForTimeout(8000)
    await shot(page, 10, 'reply-sent')
  }
  await page.goto('/runs')
  await page.getByRole('link', { name: /run-/ }).first().click()
  await shot(page, 11, 'run-viewer')
  await page.goto('/analytics')
  await shot(page, 12, 'analytics')
})
