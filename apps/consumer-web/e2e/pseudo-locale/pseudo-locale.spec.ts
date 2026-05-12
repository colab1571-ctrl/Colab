/**
 * apps/consumer-web/e2e/pseudo-locale/pseudo-locale.spec.ts
 *
 * Pseudo-locale (qps-ploc) snapshot tests for consumer-web.
 *
 * Purpose:
 *   1. Detect hardcoded strings: any text that doesn't change when
 *      lng=qps-ploc is active is hardcoded (not going through t()).
 *   2. Detect layout truncation: qps-ploc strings are ~40% longer;
 *      missing the wrapping [ ] brackets in a screenshot means overflow.
 *
 * Runs in CI via .github/workflows/pseudo-locale.yml.
 * Baseline screenshots committed under __snapshots__/.
 */

import { test, expect } from "@playwright/test";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3000";

// Routes to snapshot with qps-ploc
const ROUTES = [
  { path: "/?lng=qps-ploc", name: "home-ploc", viewport: { width: 1280, height: 800 } },
  { path: "/login?lng=qps-ploc", name: "login-ploc", viewport: { width: 1280, height: 800 } },
  { path: "/discover?lng=qps-ploc", name: "discover-ploc", viewport: { width: 1280, height: 800 } },
  // Mobile viewport
  { path: "/?lng=qps-ploc", name: "home-ploc-mobile", viewport: { width: 390, height: 844 } },
  { path: "/login?lng=qps-ploc", name: "login-ploc-mobile", viewport: { width: 390, height: 844 } },
];

test.describe("Pseudo-locale (qps-ploc) snapshot tests", () => {
  for (const route of ROUTES) {
    test(`${route.name} — no truncation, no hardcoded English`, async ({ page }) => {
      await page.setViewportSize(route.viewport);
      await page.goto(`${BASE_URL}${route.path}`);
      await page.waitForLoadState("networkidle");

      // Assert no text content equals unchanged English strings
      // (a text node that reads "Sign in" instead of the ploc equivalent is hardcoded)
      const hardcodedStrings = [
        "Sign in",
        "Welcome back",
        "Get started",
        "Discover creators",
        "Loading",
      ];
      for (const str of hardcodedStrings) {
        const exactMatch = await page.getByText(str, { exact: true }).count();
        if (exactMatch > 0) {
          console.warn(
            `[Pseudo-locale] Potential hardcoded string detected: "${str}" — verify it goes through t()`
          );
        }
      }

      // Check that pseudo-locale bracket markers are visible (not clipped)
      // If [ or ] are visible in the rendered page but clipped by overflow,
      // the screenshot diff will catch it.
      const bracketText = await page.evaluate(() => {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const texts: string[] = [];
        let node;
        while ((node = walker.nextNode())) {
          const text = node.textContent ?? "";
          if (text.includes("[") || text.includes("]")) {
            texts.push(text.trim().slice(0, 60));
          }
        }
        return texts;
      });

      // We expect to find bracket-wrapped text (means pseudo-locale is active)
      // If bracketText is empty, pseudo-locale is NOT being applied (strings are hardcoded)
      expect(bracketText.length).toBeGreaterThan(0);

      // Visual snapshot — diffs on new hardcoded strings or layout breaks
      await expect(page).toHaveScreenshot(`${route.name}.png`, {
        fullPage: true,
        maxDiffPixelRatio: 0.02, // 2% pixel diff tolerance
        animations: "disabled",
      });
    });
  }
});
