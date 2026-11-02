// Visits every console route in Chromium against the built console and fails on a missing Content-Security-Policy
// header or any securitypolicyviolation event. Starts its own API on a spare port so `make check` needs no server.
import { spawn } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { chromium } from 'playwright-core';

const root = new URL('../..', import.meta.url).pathname;
const port = 8791;
const base = `http://127.0.0.1:${port}`;
const PASSWORD = process.env.MI_DEMO_PASSWORD || 'local-demo-only';
const query = { case: '?id=inq-101', hcp: '?id=hcp-kaya' };
const pages = readdirSync(new URL('../app', import.meta.url), { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name);
const routes = ['/', ...pages.map((p) => `/${p}${query[p] || ''}`)];

const server = spawn('uv', ['run', 'uvicorn', 'hcpagents.api:app', '--port', String(port)], { cwd: root, env: { ...process.env, MI_WORKER: 'off' }, stdio: 'ignore' });
const stop = () => server.kill();
process.on('exit', stop);

for (let i = 0; ; i++) {
  try { if ((await fetch(`${base}/api/health`)).ok) break; } catch { /* still starting */ }
  if (i > 60) { console.log('csp: the API did not start'); process.exit(1); }
  await new Promise((r) => setTimeout(r, 1000));
}

const login = await fetch(`${base}/api/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user: 'u-raman', password: PASSWORD }) });
const token = (await login.json()).token;
const browser = await chromium.launch();
let bad = 0;
for (const route of routes) {
  const ctx = await browser.newContext();
  await ctx.addInitScript((t) => {
    localStorage.setItem('mi-user', 'u-raman'); sessionStorage.setItem('mi-token-u-raman', t);
    window.__violations = [];
    document.addEventListener('securitypolicyviolation', (e) => window.__violations.push(`${e.violatedDirective} ${e.blockedURI}`));
  }, token);
  const page = await ctx.newPage();
  const res = await page.goto(base + route);
  await page.waitForLoadState('networkidle');
  const header = res.headers()['content-security-policy'] || '';
  const found = await page.evaluate(() => window.__violations);
  const problems = [];
  if (!header.startsWith("default-src 'self'")) problems.push('no Content-Security-Policy header');
  if (found.length) problems.push(`violations: ${found.join('; ')}`);
  if ((await page.locator('body').innerText()).trim().length < 40) problems.push('the page rendered nothing');
  if (problems.length) { bad++; console.log(`${route}: ${problems.join(', ')}`); }
  await ctx.close();
}
await browser.close();
stop();
console.log(`csp: ${bad} problems on ${routes.length} routes`);
process.exit(bad ? 1 : 0);
