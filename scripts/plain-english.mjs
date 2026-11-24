// Plain-writing rules W1 to W14 for teach pages (docs/FRAMEWORK.md, section 4), each returning messages.
// A port of the workshop repos' scripts/plain-english.ts: proseOf, sentencesOf, syllablesIn, readingGrade
// and SIMPLER_WORDS behave the same there and here. Nothing here reads a file or exits.

export const LONGEST_SENTENCE = 25;
export const LONGEST_PARAGRAPH = 5;
// The one grade limit for every page in this repo. FRAMEWORK.md section 4 (W1): 6 or lower.
export const TEACH_GRADE = 6;

// Words that make a reader reach for a dictionary, and the everyday word to use instead.
export const SIMPLER_WORDS = {
  utilize: "use",
  utilise: "use",
  facilitate: "help",
  commence: "start",
  terminate: "end or stop",
  subsequently: "then",
  approximately: "about",
  sufficient: "enough",
  "prior to": "before",
  "in order to": "to",
  numerous: "many",
  obtain: "get",
  endeavor: "try",
  ascertain: "find out",
  thereby: "so",
  hence: "so",
  thus: "so",
  whereas: "while",
  "e.g.": "for example",
  "i.e.": "that is",
  "etc.": "the full list",
  via: "through or with",
  paradigm: "way of working",
  robust: "strong, or say what it survives",
  "in terms of": "a plainer phrase",
  "it is worth noting": "nothing; just say it",
  basically: "nothing; cut it",
  simply: "nothing; cut it",
  obviously: "nothing; cut it",
  "just ": "nothing; cut it",
};

const NUMBER_WORDS = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve";
const BANNED_HEADINGS = new Set(["introduction", "overview", "background", "notes", "misc", "details", "more"]);
// Product and brand names keep their capital letter in sentence case.
const PROPER_NOUNS = new Set(["Claude", "Temporal", "Presidio", "Playwright", "Monday", "Langfuse", "Inspect", "Graphiti", "Google", "Conftest", "Cloud", "Cedar", "Agents", "Build", "Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]);

// The fence that a line opens or closes a code block with, or "" for any other line.
const fenceOn = (line) => line.trim().match(/^`{3,}/)?.[0] ?? "";

// Which fence is open after this line: "" outside a code block.
// A block closes only on a fence at least as long as the one that opened it.
function openFenceAfter(line, openFence) {
  const fence = fenceOn(line);
  if (openFence === "") return fence;
  return fence.length >= openFence.length ? "" : openFence;
}

// Every line with the fenced code removed. Fence lines go too.
export function linesOutsideCode(markdown) {
  const kept = [];
  let openFence = "";
  for (const line of markdown.split("\n")) {
    const isFence = fenceOn(line) !== "";
    openFence = openFenceAfter(line, openFence);
    if (!isFence && openFence === "") kept.push(line);
  }
  return kept;
}

// Fenced blocks: { info, body, endLine } with endLine as the index of the closing fence.
export function codeBlocks(markdown) {
  const blocks = [];
  const lines = markdown.split("\n");
  let openFence = "";
  let current = null;
  lines.forEach((line, index) => {
    const before = openFence;
    openFence = openFenceAfter(line, openFence);
    if (before === "" && openFence !== "") current = { info: line.trim().replace(/^`+/, "").trim(), body: [], start: index };
    else if (before !== "" && openFence === "") blocks.push({ ...current, body: current.body.join("\n"), endLine: index });
    else if (before !== "") current.body.push(line);
  });
  return blocks;
}

// Keep only the lines a person reads as sentences.
export function proseOf(markdown) {
  const proseLines = [];
  let openFence = "";
  for (const line of markdown.split("\n")) {
    const isFence = fenceOn(line) !== "";
    openFence = openFenceAfter(line, openFence);
    const isStructure = /^\s*(#|\||<|!\[|Expect:)/.test(line);
    if (!isFence && openFence === "" && !isStructure) proseLines.push(line);
  }
  // Inline code stays on one line, so a stray backtick cannot hide the paragraphs after it.
  const withoutInlineCode = proseLines.join("\n").replace(/`[^`\n]*`/g, "it");
  return withoutInlineCode.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
}

export function sentencesOf(prose) {
  const paragraphs = prose.split(/\n\s*\n|\n\s*[-*\d]+[.)]?\s/);
  const sentences = paragraphs.flatMap((paragraph) => paragraph.split(/(?<=[.!?:])\s+/));
  return sentences.map((sentence) => sentence.replace(/\s+/g, " ").trim()).filter(Boolean);
}

export const wordsOf = (sentence) => sentence.match(/[A-Za-z][A-Za-z'-]*/g) ?? [];

export function syllablesIn(word) {
  const lower = word.toLowerCase().replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/, "");
  const vowelGroups = lower.match(/[aeiouy]{1,2}/g);
  return Math.max(1, vowelGroups ? vowelGroups.length : 1);
}

// Flesch-Kincaid grade level: about the school year a reader needs to follow the text.
export function readingGrade(sentences) {
  const words = sentences.flatMap(wordsOf);
  if (sentences.length === 0 || words.length === 0) return 0;
  const syllables = words.reduce((total, word) => total + syllablesIn(word), 0);
  return 0.39 * (words.length / sentences.length) + 11.8 * (syllables / words.length) - 15.59;
}

const sentencesOfPage = (markdown) => sentencesOf(proseOf(markdown));

// W1: reading grade, for a page with 5 or more sentences.
export function w1Grade(markdown, limit = TEACH_GRADE) {
  const sentences = sentencesOfPage(markdown);
  const grade = readingGrade(sentences);
  if (sentences.length >= 5 && grade > limit) return [`W1 reading grade ${grade.toFixed(1)}, above ${limit}; use shorter words`];
  return [];
}

// W2: longest sentence.
export function w2Sentences(markdown) {
  return sentencesOfPage(markdown)
    .filter((sentence) => wordsOf(sentence).length > LONGEST_SENTENCE)
    .map((sentence) => `W2 ${wordsOf(sentence).length}-word sentence "${sentence.split(" ").slice(0, 8).join(" ")}..."; split it`);
}

// W3: paragraph length. A paragraph ends at a blank line, a heading, a table row, the next list item
// or the next bold label such as **Question:**.
export function w3Paragraphs(markdown) {
  const blocks = [];
  let current = [];
  const flush = () => {
    if (current.length) blocks.push(current.join("\n"));
    current = [];
  };
  for (const line of linesOutsideCode(markdown)) {
    if (line.trim() === "" || /^\s*(#|\|)/.test(line)) flush();
    else if (/^\*\*[^*]+:\*\*/.test(line.trim())) {
      flush();
      current.push(line);
    }
    else if (/^\s*([-*]|\d+[.)])\s/.test(line)) {
      flush();
      current.push(line);
    } else current.push(line);
  }
  flush();
  const problems = [];
  for (const block of blocks) {
    const count = sentencesOf(proseOf(block)).length;
    if (count > LONGEST_PARAGRAPH) problems.push(`W3 paragraph of ${count} sentences starts "${block.trim().slice(0, 40)}"; keep it to ${LONGEST_PARAGRAPH}`);
  }
  return problems;
}

// W5: simpler words.
export function w5SimplerWords(markdown) {
  const lowerProse = ` ${proseOf(markdown).toLowerCase()} `;
  const problems = [];
  for (const [hardWord, simpler] of Object.entries(SIMPLER_WORDS)) {
    const escaped = hardWord.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp(`[^a-z]${escaped}(?![a-z])`).test(lowerProse)) problems.push(`W5 "${hardWord.trim()}": write ${simpler}`);
  }
  return problems;
}

// W6: passive voice. At most 1 in 10 sentences has a form of "be" and then a word ending in -ed.
export function w6Passive(markdown) {
  const sentences = sentencesOfPage(markdown);
  const passive = sentences.filter((sentence) => /\b(is|are|was|were|be|been|being)\s+(\w+ly\s+)?(?!need|speed|seed|feed|embed)\w{2,}ed\b/i.test(sentence));
  if (passive.length * 10 > sentences.length) {
    return [`W6 ${passive.length} of ${sentences.length} sentences are passive, for example "${passive[0].split(" ").slice(0, 8).join(" ")}..."; name who acts`];
  }
  return [];
}

// W7 and W8 read the headings. A part page prefixes its title with the folder name, which is dropped.
export function headingTexts(markdown) {
  return linesOutsideCode(markdown)
    .map((line) => line.match(/^#{1,6}\s+(.+?)\s*$/)?.[1])
    .filter(Boolean)
    .map((text) => text.replace(/^\d\d-[a-z0-9-]+:\s*/, ""));
}

export function w7w8Headings(markdown) {
  const problems = [];
  for (const heading of headingTexts(markdown)) {
    const words = heading.replace(/`[^`]*`/g, "").split(/\s+/).filter(Boolean);
    if (BANNED_HEADINGS.has(heading.toLowerCase())) problems.push(`W7 heading "${heading}" does not name a job`);
    if (/\.$/.test(heading)) problems.push(`W8 heading "${heading}" ends with a period`);
    const capitalised = words.slice(1).filter((word) => /^[A-Z][a-z]+$/.test(word) && !PROPER_NOUNS.has(word));
    if (capitalised.length) problems.push(`W8 heading "${heading}" is not sentence case: ${capitalised.join(", ")}`);
    // A count starts the heading ("Two checks") or uses digits ("3 steps"). "One job" mid-heading is not a count.
    const count = new RegExp(`^(\\d+|${NUMBER_WORDS})\\s+[a-z]|\\d+\\s+[a-z]`, "i");
    if (count.test(heading)) problems.push(`W8 heading "${heading}" has a count`);
    const ordinal = new RegExp(`\\b(lab|part|step|week|day|module|session|stage)\\s+(\\d+|${NUMBER_WORDS})\\b|^(first|second|third|fourth|fifth)\\b`, "i");
    if (ordinal.test(heading)) problems.push(`W8 heading "${heading}" has an ordinal label`);
  }
  return problems;
}

// W9: no em dashes.
export function w9EmDash(markdown) {
  return markdown.includes("—") ? ["W9 contains an em dash"] : [];
}

// W10: every bash block is followed by an Expect: line.
export function w10Expect(markdown) {
  const lines = markdown.split("\n");
  return codeBlocks(markdown)
    .filter((block) => /^(bash|sh|shell)\b/.test(block.info))
    .filter((block) => !(lines.slice(block.endLine + 1).find((line) => line.trim() !== "") ?? "").trim().startsWith("Expect:"))
    .map((block) => `W10 the bash block at line ${block.start + 1} has no Expect: line after it`);
}

// W11: link text.
export function w11Links(markdown) {
  const problems = [];
  const text = linesOutsideCode(markdown).join("\n");
  for (const [, label] of text.matchAll(/\[([^\]]*)\]\([^)]*\)/g)) {
    if (/^(here|click here|this link|link|this page)$/i.test(label.trim())) problems.push(`W11 link text "${label}" says nothing about the target`);
    if (/^(https?:\/\/|www\.)/i.test(label.trim())) problems.push(`W11 a bare URL is the link text: ${label}`);
  }
  return problems;
}

// W12: no direction words for page parts.
export function w12Directions(markdown) {
  const prose = proseOf(markdown).toLowerCase();
  return [...new Set(prose.match(/\b(above|below|on the left|on the right)\b/g) ?? [])].map((word) => `W12 direction word "${word}"`);
}

// W13: a teaching page shows an example.
export function w13Example(markdown) {
  return /\bfor example\b/i.test(markdown) ? [] : ['W13 no "For example": show one real case, not only the rule'];
}

// W14 (warning): a comment that only repeats the identifiers on the next line.
export function w14Comments(markdown) {
  const warnings = [];
  for (const block of codeBlocks(markdown)) {
    const lines = block.body.split("\n");
    lines.forEach((line, index) => {
      const comment = line.match(/^\s*(?:#|\/\/)\s*(.+)$/)?.[1];
      const next = lines.slice(index + 1).find((candidate) => candidate.trim() !== "");
      if (!comment || !next) return;
      const words = comment.toLowerCase().match(/[a-z0-9]+/g) ?? [];
      const identifiers = new Set(next.replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase().match(/[a-z0-9]+/g) ?? []);
      if (words.length >= 3 && words.every((word) => identifiers.has(word))) warnings.push(`W14 comment "${comment}" repeats the next line; say why`);
    });
  }
  return warnings;
}
