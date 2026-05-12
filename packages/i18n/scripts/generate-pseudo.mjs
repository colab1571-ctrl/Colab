#!/usr/bin/env node
/**
 * packages/i18n/scripts/generate-pseudo.mjs
 *
 * Generates the qps-ploc (Microsoft pseudo-locale) locale files from the
 * English source strings. Run this script whenever en/ locale files change.
 *
 * Usage:
 *   node packages/i18n/scripts/generate-pseudo.mjs
 *
 * Output:
 *   packages/i18n/locales/qps-ploc/<ns>.json  (all 13 namespaces)
 *
 * Algorithm (per string value):
 *   1. Wrap in [ … ] — truncation detector.
 *   2. Substitute Latin characters with decorated Unicode equivalents.
 *   3. Append " Ééxxpáändéd!!" — ~40% length expansion.
 *   4. Inject Unicode LRE/PDF bidi markers to verify bidi-neutrality.
 *   ICU placeholders ({name}, {count, plural, …}) are left untouched.
 *
 * DO NOT hand-edit the qps-ploc/ files — they are regenerated automatically.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const EN_DIR = path.resolve(__dirname, "../locales/en");
const PLOC_DIR = path.resolve(__dirname, "../locales/qps-ploc");

// qps-ploc character map: Latin → decorated Unicode
const CHAR_MAP = {
  a: "á", A: "Á",
  b: "ƀ", B: "Ɓ",
  c: "ć", C: "Ć",
  d: "ď", D: "Ď",
  e: "é", E: "É",
  f: "ƒ", F: "Ƒ",
  g: "ĝ", G: "Ĝ",
  h: "ĥ", H: "Ĥ",
  i: "í", I: "Í",
  j: "ĵ", J: "Ĵ",
  k: "ķ", K: "Ķ",
  l: "ĺ", L: "Ĺ",
  m: "m̂", M: "M̂",
  n: "ñ", N: "Ñ",
  o: "ó", O: "Ó",
  p: "ƥ", P: "Ƥ",
  q: "q̈", Q: "Q̈",
  r: "ŕ", R: "Ŕ",
  s: "ś", S: "Ś",
  t: "ţ", T: "Ţ",
  u: "ú", U: "Ú",
  v: "v̂", V: "V̂",
  w: "ŵ", W: "Ŵ",
  x: "x̂", X: "X̂",
  y: "ý", Y: "Ý",
  z: "ź", Z: "Ź",
};

// Unicode bidi markers
const LRE = "‪"; // Left-to-Right Embedding
const PDF = "‬"; // Pop Directional Formatting

/**
 * Pseudolocalise a single string value.
 * ICU placeholders like {name}, {count, plural, …} are preserved verbatim.
 */
function pseudolocalise(str) {
  if (typeof str !== "string") return str;

  // Split on ICU placeholder groups to preserve them
  // Match simple {name} and complex {name, type, ...} including nested braces
  const parts = [];
  let i = 0;
  while (i < str.length) {
    if (str[i] === "{") {
      // Find matching closing brace (account for nesting)
      let depth = 0;
      let j = i;
      while (j < str.length) {
        if (str[j] === "{") depth++;
        else if (str[j] === "}") {
          depth--;
          if (depth === 0) break;
        }
        j++;
      }
      parts.push({ type: "placeholder", text: str.slice(i, j + 1) });
      i = j + 1;
    } else {
      // Collect literal characters until next {
      let j = i;
      while (j < str.length && str[j] !== "{") j++;
      parts.push({ type: "literal", text: str.slice(i, j) });
      i = j;
    }
  }

  // Transform literals
  const transformed = parts.map((part) => {
    if (part.type === "placeholder") return part.text;
    // Substitute characters
    return part.text
      .split("")
      .map((ch) => CHAR_MAP[ch] ?? ch)
      .join("");
  }).join("");

  // Assemble with bidi markers, brackets, and expansion suffix
  return `${LRE}[${transformed} Ééxxpáändéd!!]${PDF}`;
}

/**
 * Recursively pseudolocalise all string values in an object.
 * Non-string values (numbers, booleans) are passed through.
 * Nested objects are recursed.
 */
function pseudolocaliseObject(obj) {
  if (typeof obj === "string") return pseudolocalise(obj);
  if (typeof obj !== "object" || obj === null) return obj;
  if (Array.isArray(obj)) return obj.map(pseudolocaliseObject);
  const out = {};
  for (const [key, val] of Object.entries(obj)) {
    out[key] = pseudolocaliseObject(val);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const namespaces = fs.readdirSync(EN_DIR).filter((f) => f.endsWith(".json"));

fs.mkdirSync(PLOC_DIR, { recursive: true });

let count = 0;
for (const ns of namespaces) {
  const enPath = path.join(EN_DIR, ns);
  const plocPath = path.join(PLOC_DIR, ns);

  const enData = JSON.parse(fs.readFileSync(enPath, "utf8"));
  const plocData = pseudolocaliseObject(enData);

  fs.writeFileSync(plocPath, JSON.stringify(plocData, null, 2) + "\n", "utf8");
  count++;
  console.log(`✓ Generated qps-ploc/${ns}`);
}

console.log(`\nDone — ${count} namespace(s) written to locales/qps-ploc/`);
console.log("Note: these files are auto-generated. Do not edit by hand.");
