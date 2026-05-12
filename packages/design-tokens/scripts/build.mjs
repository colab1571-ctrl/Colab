#!/usr/bin/env node
/**
 * Design token build script.
 * Runs Style Dictionary and then writes platform-specific wrapper files.
 *
 * Usage: node scripts/build.mjs
 */

import StyleDictionary from "style-dictionary";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");

// Run Style Dictionary
const sd = new StyleDictionary(path.join(root, "style-dictionary.config.mjs"));
await sd.buildAllPlatforms();

// ---------------------------------------------------------------------------
// Post-process: write a human-friendly CSS file that uses @theme (Tailwind v4)
// ---------------------------------------------------------------------------
const cssInput = path.join(root, "build/css/tokens.css");
const tailwindCssOutput = path.join(root, "build/css/tailwind-theme.css");

if (fs.existsSync(cssInput)) {
  const raw = fs.readFileSync(cssInput, "utf-8");
  // Convert :root { --colab-... } to @theme { --colab-... }
  const tailwindTheme = raw.replace(/:root\s*\{/, "@theme {");
  fs.writeFileSync(tailwindCssOutput, tailwindTheme);
  console.log("✓ Tailwind v4 @theme CSS written to build/css/tailwind-theme.css");
}

// ---------------------------------------------------------------------------
// A11y contrast check (basic — full audit in spec 018)
// ---------------------------------------------------------------------------
const tokensJson = path.join(root, "tokens/colors.json");
const colors = JSON.parse(fs.readFileSync(tokensJson, "utf-8"));

let a11yFailed = false;
const brandPairs = colors.color?.brand ?? {};
for (const [name, token] of Object.entries(brandPairs)) {
  const contrast = token.a11y?.contrast_on_white;
  if (contrast !== undefined && contrast < 4.5) {
    console.error(
      `A11Y FAIL: color.brand.${name} contrast on white = ${contrast} (required ≥ 4.5 WCAG AA)`
    );
    a11yFailed = true;
  }
}

if (a11yFailed) {
  process.exit(1);
} else {
  console.log("✓ A11y contrast check passed.");
}

console.log("✓ Design token build complete.");
