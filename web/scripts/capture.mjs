// Captures every screen docs/product-walkthrough.md links, in the order the walkthrough tells the story,
// from a running console (`make serve`) on freshly provisioned data with every inbox inquiry run.
// scripts/walkthrough.sh prepares that state, runs this and converts the PNGs to WebP.
// Writes <out>/<screen>-desktop.png: the 1440x900 window as a viewer sees it. FULL=1 captures whole pages.
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from 'playwright-core';

const out = process.argv[2];
if (!out) throw new Error('usage: node scripts/capture.mjs <out-dir>');
const base = process.env.MI_CONSOLE || 'http://localhost:8765';
const full = process.env.FULL === '1';

const click = (name) => async (page) => {
  await page.getByRole('button', { name }).first().click();
  await page.locator('.toast').first().waitFor();
};
const reach = (sel) => async (page) => page.locator(sel).first().scrollIntoViewIfNeeded();
// for a block taller than the window: put the top of its section at the top
const top = (sel) => async (page) => page.locator(sel).first().evaluate((e) => e.closest('section').scrollIntoView());

// One entry per screen section in the doc. Order matters: withdraw happens before the blocked approval.
export const screens = [
  { name: 'architecture', at: '/' },
  { name: 'routing-table', at: '/', act: reach('#rules') },
  { name: 'inbox', at: '/inbox' },
  { name: 'case-sent', at: '/case?id=inq-101', act: reach('.staple') },
  { name: 'case-review', at: '/case?id=inq-103', act: reach('.decide') },
  { name: 'case-adverse-event', at: '/case?id=inq-105', act: reach('.stamp') },
  { name: 'case-injection', at: '/case?id=inq-107', act: reach('.stamp') },
  { name: 'case-off-label', at: '/case?id=inq-104', act: reach('.stamp') },
  { name: 'case-guards', at: '/case?id=inq-101', act: reach('#calls') },
  { name: 'review-bench', at: '/review' },
  { name: 'hcp-360', at: '/hcp?id=hcp-kaya', act: reach('#detail') },
  { name: 'field-rep-denied', at: '/case?id=inq-105', as: 'u-becker' },
  { name: 'withdraw-content', at: '/content', as: 'u-weber', act: async (page) => {
    await page.locator('[data-w="VEL-DE-RENAL"]').scrollIntoViewIfNeeded();
    await page.locator('[data-w="VEL-DE-RENAL"]').click();
    await page.locator('.toast').first().waitFor();
  } },
  { name: 'approve-blocked', at: '/case?id=inq-103', as: 'u-brandt', act: async (page) => {
    await click('Approve and send')(page);
    await page.locator('.staple li.bad').first().waitFor();
    await page.locator('.staple').scrollIntoViewIfNeeded();
  } },
  { name: 'wrong-country-reviewer', at: '/case?id=inq-112', as: 'u-hale', act: async (page) => {
    await page.locator('.decide').scrollIntoViewIfNeeded();
    await click('Approve and send')(page);
  } },
  { name: 'proof', at: '/proof' },
  { name: 'ledger-tamper', at: '/proof', act: async (page) => {
    await click('Change a past entry')(page);
    await page.locator('#ledgercard').scrollIntoViewIfNeeded();
  } },
  { name: 'archive-locked', at: '/proof', act: async (page) => {
    await click('Restore from the archive')(page);
    await page.locator('.toast').first().waitFor({ state: 'detached' });
    await click('Try to delete the archive')(page);
    await page.locator('#ledgercard').scrollIntoViewIfNeeded();
  } },
  { name: 'kill-switch', at: '/proof', act: reach('#autonomy') },
  { name: 'release-gate', at: '/proof', act: top('#evals') },
];

if (import.meta.url === `file://${process.argv[1]}`) {
  mkdirSync(out, { recursive: true });
  const only = process.env.WALKTHROUGH_SCREENS?.split(',');
  const browser = await chromium.launch();
  try {
    for (const s of screens) {
      if (only && !only.includes(s.name)) continue;
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-US', timezoneId: 'UTC', reducedMotion: 'reduce', colorScheme: 'light' });
      await ctx.addInitScript((id) => localStorage.setItem('mi-user', id), s.as || 'u-raman');
      const page = await ctx.newPage();
      const errors = [];
      page.on('pageerror', (e) => errors.push(e.message));
      // a 403 the screen is meant to show is logged by the browser; anything else is a bug
      page.on('console', (m) => m.type() === 'error' && !/status of 403/.test(m.text()) && errors.push(m.text()));
      const res = await page.goto(base + s.at);
      if (!res?.ok()) throw new Error(`${s.name}: HTTP ${res?.status()} at ${s.at}`);
      await page.waitForLoadState('networkidle');
      if (s.act) await s.act(page);
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: join(out, `${s.name}-desktop.png`), fullPage: full, animations: 'disabled' });
      await ctx.close();
      if (errors.length) throw new Error(`${s.name}: ${errors.join('; ')}`);
      console.log(`captured ${s.name}`);
    }
  } finally {
    await browser.close();
  }
}
