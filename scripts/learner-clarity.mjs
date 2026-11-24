// Learner-page clarity gate (docs/CLARITY.md rules 1 and 5); run from a workshop root, exits 1 on a problem.
// Teach holds the source: workshop copies of this file and plain-english.mjs must match byte for byte
// (scripts/check-learner-copies.mjs). Scope and skipped folders are in inScope; meaning is left to a reader.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { w1Grade } from "./plain-english.mjs";

export const LONGEST_SENTENCE = 25;
export const LONGEST_PARAGRAPH = 5;

const SKIPPED = new Set([
  "node_modules",
  ".git",
  "wrong",
  "research",
  "solution",
  "fixtures",
  "recordings",
  ".venv",
  "case-studies",
  "evidence",
]);

// Lines that end a paragraph without being prose: headings, tables, HTML and images.
const BREAK_PREFIXES = ["#", "|", "<", "!["];
const LIST_ITEM = /^(\d+\.|-|\*)\s+/;
const MINUTES = /\b\d+\s*(minutes?|mins?)\b/i;

const PROSE_RULES = [
  { pattern: /—/, message: "em dash: use a full stop or a comma" },
  { pattern: /;\s/, message: "semicolon: use a full stop or a comma" },
  {
    pattern: MINUTES,
    message: "exact minutes: say what the step does, not how long it takes",
  },
];

export function inScope(rel) {
  if (rel.split("/").some((part) => SKIPPED.has(part))) return false;
  if (rel === "README.md" || rel.startsWith("00-") || rel.startsWith("docs/learner/")) return rel.endsWith(".md");
  if (rel.startsWith("parts/")) {
    return rel.endsWith("README.md") || rel.endsWith("troubleshooting.md");
  }
  return false;
}

export function learnerPages(root, dir = root, out = []) {
  for (const name of readdirSync(dir).sort()) {
    if (SKIPPED.has(name)) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      learnerPages(root, full, out);
    } else if (name.endsWith(".md")) {
      const rel = relative(root, full);
      if (inScope(rel)) out.push(rel);
    }
  }
  return out;
}

function isBreakLine(line) {
  // Expect lines are checked by verify, and their wording is kept exactly, so they are not prose.
  if (!line || line.startsWith("Expect:")) return true;
  return BREAK_PREFIXES.some((prefix) => line.startsWith(prefix));
}

// Inline code becomes the word "code", so a command counts as one word.
function proseOf(line) {
  return line.replace(/`[^`]*`/g, "code").replace(LIST_ITEM, "");
}

// Prose lines of a page, grouped into paragraphs. Code blocks, headings, tables, images and
// HTML are dropped.
export function paragraphsOf(text) {
  const withoutCode = text.replace(/```[\s\S]*?```/g, "");
  const paragraphs = [];
  let current = [];
  const flush = () => {
    if (current.length) paragraphs.push(current.join(" "));
    current = [];
  };
  for (const raw of withoutCode.split("\n")) {
    const line = raw.trim();
    if (isBreakLine(line)) {
      flush();
      continue;
    }
    // A list item is its own paragraph. Other lines wrapped in the source belong to one paragraph.
    if (LIST_ITEM.test(line)) flush();
    current.push(proseOf(line));
  }
  flush();
  return paragraphs;
}

export function sentencesOf(paragraph) {
  return paragraph.split(/(?<=[.!?])\s+/).filter((sentence) => sentence.trim() !== "");
}

function sentenceProblems(sentence) {
  const words = sentence.split(/\s+/).length;
  if (words <= LONGEST_SENTENCE) return [];
  const preview = sentence.slice(0, 70);
  return [`sentence has ${words} words; keep it to ${LONGEST_SENTENCE} or fewer: "${preview}..."`];
}

function paragraphProblems(paragraph) {
  const sentences = sentencesOf(paragraph);
  const problems = [];
  if (sentences.length > LONGEST_PARAGRAPH) {
    problems.push(
      `paragraph has ${sentences.length} sentences; ` + `keep it to ${LONGEST_PARAGRAPH} or fewer`,
    );
  }
  for (const sentence of sentences) {
    problems.push(...sentenceProblems(sentence));
  }
  for (const rule of PROSE_RULES) {
    if (rule.pattern.test(paragraph)) problems.push(rule.message);
  }
  return problems;
}

// The problems in one page's text, as plain messages.
export function pageProblems(text) {
  return [...w1Grade(text), ...paragraphsOf(text).flatMap(paragraphProblems)];
}

export function run(root) {
  const failures = [];
  for (const rel of learnerPages(root)) {
    const text = readFileSync(join(root, rel), "utf8");
    for (const problem of pageProblems(text)) {
      failures.push(`${rel}: ${problem}`);
    }
  }
  return failures;
}

function report(failures) {
  console.log("Learner pages are not clear enough yet:");
  for (const failure of failures) console.log(`  ${failure}`);
  console.log(
    `${failures.length} problem(s). Fix the words, ` +
      "keep every code block, Expect line and token the same.",
  );
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const failures = run(process.cwd());
  if (failures.length > 0) {
    report(failures);
    process.exit(1);
  }
  console.log(
    "Learner pages pass: grade 6 or below, every sentence 25 words or fewer, " +
      "every paragraph 5 sentences or fewer.",
  );
}
