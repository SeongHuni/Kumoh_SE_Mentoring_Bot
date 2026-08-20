const fs = require("fs");

const HANGUL_LIST_ORDER = "가나다라마바사아자차카타파하";

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function jsonlStringify(rows) {
  return rows.map((row) => JSON.stringify(row)).join("\n") + "\n";
}

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) * p)];
}

function countBy(rows, selector) {
  return rows.reduce((acc, row) => {
    const key = selector(row) || "(missing)";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function estimateTokenCount(text) {
  let total = 0;
  const parts = String(text || "").match(/https?:\/\/\S+|[A-Za-z0-9_]+|\s+|./gsu) || [];

  for (const part of parts) {
    if (/^\s+$/u.test(part)) continue;
    if (/^https?:\/\//u.test(part)) {
      total += Math.max(1, Math.ceil(part.length / 6));
    } else if (/^[A-Za-z0-9_]+$/u.test(part)) {
      total += Math.max(1, Math.ceil(part.length / 4));
    } else if (/^[.,!?;:()[\]{}"'`~@#$%^&*_+=/\\|-]$/u.test(part)) {
      total += 1;
    } else {
      total += Array.from(part).length;
    }
  }

  return total;
}

function hardSplitByTokenEstimate(text, maxTokens) {
  const parts = String(text || "").match(/https?:\/\/\S+|[A-Za-z0-9_]+|\s+|./gsu) || [];
  const chunks = [];
  let current = "";
  let currentTokens = 0;

  for (const part of parts) {
    const partTokens = estimateTokenCount(part);
    if (current && currentTokens + partTokens > maxTokens) {
      chunks.push(current.trim());
      current = "";
      currentTokens = 0;
    }
    current += part;
    currentTokens += partTokens;
  }

  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

function stripExistingHeader(pageContent) {
  const text = String(pageContent || "").replace(/\r\n/g, "\n");
  if (!text.startsWith("제목:")) return text.trim();

  const blankLineIndex = text.indexOf("\n\n");
  if (blankLineIndex === -1) return text.trim();
  return text.slice(blankLineIndex + 2).trim();
}

function buildHeader(metadata) {
  const lines = [];
  if (metadata.title) lines.push(`제목: ${metadata.title}`);
  if (metadata.source) lines.push(`출처: ${metadata.source}`);
  if (metadata.category) lines.push(`분류: ${metadata.category}`);
  if (metadata.published_at) lines.push(`작성일: ${metadata.published_at}`);
  return lines.join("\n");
}

function splitSentences(text) {
  const trimmed = String(text || "").replace(/\r\n/g, "\n").trim();
  if (!trimmed) return [];

  const sentences = trimmed
    .replace(/([.!?。！？]|(?:다|요|니다|음|함)\.)\s+/gu, "$1\n")
    .split(/\n+/u)
    .map((part) => part.trim())
    .filter(Boolean);

  return sentences.length ? sentences : [trimmed];
}

function markerRank(marker) {
  if (/^\d+$/u.test(marker)) return { kind: "digit", value: Number(marker) };
  const value = HANGUL_LIST_ORDER.indexOf(marker);
  return { kind: "hangul", value };
}

// Inline enumeration markers ("1. ... 2. ...", "가. ... 나. ...") appear in this dataset
// with no preceding newline, so they can't be detected by newline-gated splitting. The
// risk is false positives on things like Korean date fragments ("2026. 7. 9.(목)"), so a
// candidate run is only trusted as a real list when it forms a monotonic run of >=2
// distinct increasing values starting at 1 or 2 (digits) — dates rarely satisfy this
// because they don't restart near 1 and repeat the same day/month across a paragraph.
// A digit marker immediately preceded by "<digit>. " (e.g. the "7." inside "2026. 7. 9.")
// is almost always a date fragment, not a list item — real list items in this corpus
// follow a sentence ending (Hangul + "다./요./니다." + space) or another marker's content,
// never another bare number-dot. Reject those at the source so they can't break the
// monotonicity check for the real enumeration.
function looksLikeDateContinuation(text, matchIndex) {
  const before = text.slice(Math.max(0, matchIndex - 8), matchIndex);
  return /\d[.]\s*$/u.test(before);
}

// NOTE: must list the 14 list letters explicitly (not a `가-하` Unicode range), since
// Hangul syllables aren't laid out in 가나다-order in Unicode — a range would match
// hundreds of unrelated syllables (e.g. "다" in "바랍니다") that happen to fall between
// 가 and 하 by code point.
// The `(?<!\S)` lookbehind requires the marker char to be its own token (preceded by
// whitespace or start-of-string) — without it, "다" as the final syllable of an ordinary
// verb ending ("...바랍니다.") would falsely match as list-marker "다.", since 다 is
// legitimately one of the 14 letters (가나["다"]라...).
const MARKER_REGEX = new RegExp("(?<!\\S)(\\d{1,2}|[" + HANGUL_LIST_ORDER + "])[.)]\\s+(?=\\S)", "gu");

function findValidatedMarkerBoundaries(text) {
  const regex = new RegExp(MARKER_REGEX.source, MARKER_REGEX.flags);
  const candidates = [];
  let match = regex.exec(text);
  while (match) {
    const rank = markerRank(match[1]);
    if (rank.kind === "hangul" && rank.value === -1) {
      match = regex.exec(text);
      continue;
    }
    if (rank.kind === "digit" && looksLikeDateContinuation(text, match.index)) {
      match = regex.exec(text);
      continue;
    }
    candidates.push({ index: match.index, kind: rank.kind, value: rank.value });
    match = regex.exec(text);
  }

  function validateRun(run, requireLowStart) {
    if (run.length < 2) return new Set();
    if (requireLowStart && run[0].value !== 1 && run[0].value !== 2) return new Set();

    let prev = -Infinity;
    let distinctIncreasing = 0;
    for (const candidate of run) {
      if (candidate.value < prev) return new Set();
      if (candidate.value > prev) distinctIncreasing += 1;
      prev = candidate.value;
    }

    return distinctIncreasing >= 2 ? new Set(run.map((c) => c.index)) : new Set();
  }

  const digitRun = candidates.filter((c) => c.kind === "digit");
  const hangulRun = candidates.filter((c) => c.kind === "hangul");
  const validDigits = validateRun(digitRun, true);
  const validHangul = validateRun(hangulRun, false);

  return candidates
    .filter((c) => validDigits.has(c.index) || validHangul.has(c.index))
    .map((c) => c.index)
    .sort((a, b) => a - b);
}

function splitInlineMarkers(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return [];

  const boundaries = findValidatedMarkerBoundaries(trimmed);
  if (!boundaries.length) return [trimmed];

  const pieces = [];
  let start = 0;
  for (const boundary of boundaries) {
    if (boundary > start) pieces.push(trimmed.slice(start, boundary).trim());
    start = boundary;
  }
  pieces.push(trimmed.slice(start).trim());
  return pieces.filter(Boolean);
}

function splitBlankParagraph(text) {
  return text
    .split(/\n{2,}/u)
    .map((part) => part.trim())
    .filter(Boolean);
}

function splitNewline(text) {
  return text
    .split(/\n/u)
    .map((part) => part.trim())
    .filter(Boolean);
}

// Splits text at every occurrence of a keyword-anchor regex (e.g. "신청기간|신청방법|..."),
// keeping the keyword attached to the start of the new piece — used for document-specific
// splitting where administrative field labels should win as boundaries even without any
// punctuation/newline support. Needs >=2 matches to "fire" as a tier (consistent with the
// other tiers returning a single piece when their separator is absent).
function splitByKeywordAnchors(text, keywordRegex) {
  const flags = keywordRegex.flags.includes("g") ? keywordRegex.flags : `${keywordRegex.flags}g`;
  const regex = new RegExp(keywordRegex.source, flags);
  const boundaries = [];
  let match = regex.exec(text);
  while (match) {
    if (!boundaries.length || match.index > boundaries[boundaries.length - 1]) {
      boundaries.push(match.index);
    }
    match = regex.exec(text);
  }
  if (boundaries.length < 2) return [text];

  const pieces = [];
  let start = 0;
  for (const boundary of boundaries) {
    if (boundary > start) pieces.push(text.slice(start, boundary).trim());
    start = boundary;
  }
  pieces.push(text.slice(start).trim());
  return pieces.filter(Boolean);
}

function makeKeywordAnchorTier(name, keywordRegex) {
  return { name, split: (text) => splitByKeywordAnchors(text, keywordRegex) };
}

const SEPARATOR_TIERS = [
  { name: "blank_paragraph", split: splitBlankParagraph },
  { name: "newline", split: splitNewline },
  { name: "inline_marker", split: splitInlineMarkers },
  { name: "sentence", split: splitSentences },
];

// Recursive-descent splitter: try the coarsest separator tier first; if it doesn't fire
// (produces <=1 piece, meaning the separator isn't present) fall through to the next
// finer tier. Each resulting piece is only re-split with FINER tiers than the one that
// produced it, matching standard recursive-character-splitter semantics.
function recursiveSegments(text, maxTokens, tierIndex = 0, tiers = SEPARATOR_TIERS) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return [];
  if (estimateTokenCount(trimmed) <= maxTokens) return [trimmed];
  if (tierIndex >= tiers.length) return hardSplitByTokenEstimate(trimmed, maxTokens);

  const pieces = tiers[tierIndex].split(trimmed);
  if (pieces.length <= 1) return recursiveSegments(trimmed, maxTokens, tierIndex + 1, tiers);

  return pieces.flatMap((piece) =>
    estimateTokenCount(piece) > maxTokens
      ? recursiveSegments(piece, maxTokens, tierIndex + 1, tiers)
      : [piece]
  );
}

// Greedy-packs pre-split leaf segments into chunks up to maxTokens, preserving order.
// A single leaf that already exceeds maxTokens is hard-split rather than dropped.
function packLeavesToChunks(leaves, maxTokens) {
  const chunks = [];
  let current = "";
  let currentTokens = 0;

  for (const leaf of leaves) {
    const leafTokens = estimateTokenCount(leaf);

    if (leafTokens > maxTokens) {
      if (current.trim()) {
        chunks.push(current.trim());
        current = "";
        currentTokens = 0;
      }
      chunks.push(...hardSplitByTokenEstimate(leaf, maxTokens));
      continue;
    }

    if (current && currentTokens + leafTokens > maxTokens) {
      chunks.push(current.trim());
      current = leaf;
      currentTokens = leafTokens;
    } else {
      current = current ? `${current}\n${leaf}` : leaf;
      currentTokens += leafTokens;
    }
  }

  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

// Reads outputs/chunking_experiments/manifest.json if present and appends/replaces
// entries by experiment name, instead of overwriting the whole file — so new chunking
// scripts can add experiments without clobbering the existing A-F entries.
function mergeManifest(manifestPath, sourceFile, documentCount, newEntries) {
  let manifest = {
    source_file: sourceFile,
    document_count: documentCount,
    experiments: [],
    created_at: new Date().toISOString(),
  };

  if (fs.existsSync(manifestPath)) {
    manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  }

  const byName = new Map((manifest.experiments || []).map((entry) => [entry.experiment, entry]));
  for (const entry of newEntries) {
    byName.set(entry.experiment, entry);
  }

  manifest.experiments = Array.from(byName.values());
  manifest.updated_at = new Date().toISOString();

  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  return manifest;
}

module.exports = {
  ensureDir,
  jsonlStringify,
  percentile,
  countBy,
  estimateTokenCount,
  hardSplitByTokenEstimate,
  stripExistingHeader,
  buildHeader,
  splitSentences,
  splitInlineMarkers,
  splitBlankParagraph,
  splitNewline,
  splitByKeywordAnchors,
  makeKeywordAnchorTier,
  recursiveSegments,
  packLeavesToChunks,
  mergeManifest,
  SEPARATOR_TIERS,
};
