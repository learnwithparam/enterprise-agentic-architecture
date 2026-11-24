// Runs teach's learner clarity rules on README.md and every lab page.
// learner-clarity.mjs and plain-english.mjs are byte-for-byte copies from the teach repo
// (teach's check-learner-copies.mjs fails a drift). Teach scopes the check to its own folders,
// so this file adds labs/ here instead of changing the shared copy.
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { learnerPages, pageProblems, run } from "./learner-clarity.mjs";

const root = process.cwd();
const failures = run(root);
const pages = ["labs/README.md"];
for (const name of readdirSync(join(root, "labs")).sort()) {
  const rel = `labs/${name}/README.md`;
  if (existsSync(join(root, rel))) pages.push(rel);
}
for (const rel of pages) {
  for (const problem of pageProblems(readFileSync(join(root, rel), "utf8"))) failures.push(`${rel}: ${problem}`);
}
if (failures.length > 0) {
  console.log("Learner pages are not clear enough yet:");
  for (const failure of failures) console.log(`  ${failure}`);
  console.log(`${failures.length} problem(s). Fix the words, keep every code block, Expect line and token the same.`);
  process.exit(1);
}
console.log(`${pages.length + learnerPages(root).length} learner pages pass: grade 6 or below, sentences of 25 words or fewer, paragraphs of 5 sentences or fewer.`);
