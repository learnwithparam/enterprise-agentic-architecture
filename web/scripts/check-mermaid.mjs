// Parse every ```mermaid block in the repo's Markdown with the pinned mermaid build, in the
// Chromium shell playwright-core installs. A block GitHub would refuse to render fails make check.
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { chromium } from 'playwright-core';

const root = new URL('../..', import.meta.url).pathname;
const skip = new Set(['node_modules', '.venv', '.git', 'dist', '$S']);
const files = [];
const walk = (dir) => {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (skip.has(e.name)) continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith('.md')) files.push(p);
  }
};
walk(root);

const blocks = files.flatMap((f) =>
  [...readFileSync(f, 'utf8').matchAll(/```mermaid\n([\s\S]*?)```/g)].map((m, i) => ({ where: `${relative(root, f)} block ${i + 1}`, code: m[1] })));

const browser = await chromium.launch();
const page = await browser.newPage();
await page.addScriptTag({ path: new URL('../node_modules/mermaid/dist/mermaid.min.js', import.meta.url).pathname });
let bad = 0;
for (const b of blocks) {
  const err = await page.evaluate(async (code) => {
    try { await window.mermaid.parse(code); return null; } catch (e) { return String(e.message || e).split('\n').slice(0, 4).join('\n'); }
  }, b.code);
  if (err) { bad++; console.log(`${b.where}: ${err}`); }
}
await browser.close();
console.log(`mermaid: ${bad} problems in ${blocks.length} blocks`);
process.exit(bad ? 1 : 0);
