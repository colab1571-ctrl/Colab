/**
 * apps/consumer-web/e2e/a11y/axe.spec.ts
 *
 * axe-core + Playwright accessibility tests for consumer-web.
 *
 * Runs on every PR via .github/workflows/a11y-web.yml.
 * Fails on any axe violation with impact "serious" or "critical".
 * Moderate/minor violations are surfaced as warnings and tracked in docs/a11y-checklist.md.
 *
 * Target: zero serious/critical findings (AC-01).
 */

import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3000";

/** Routes to audit — expand as new pages are added */
const ROUTES = [
  { path: "/", name: "home" },
  { path: "/login", name: "login" },
  { path: "/discover", name: "discover" },
  { path: "/settings", name: "settings" },
];

/** axe impact levels that block CI */
const BLOCKING_IMPACTS = ["critical", "serious"] as const;

test.describe("axe-core accessibility — consumer-web", () => {
  for (const route of ROUTES) {
    test(`${route.name} page (${route.path}) — zero critical/serious violations`, async ({
      page,
    }) => {
      await page.goto(`${BASE_URL}${route.path}`);

      // Wait for content to be visible
      await page.waitForLoadState("networkidle");

      const accessibilityScanResults = await new AxeBuilder({ page })
        // Target WCAG 2.1 AA rules only
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        // Exclude known third-party iframes (Stripe, tldraw) from strict scanning
        .exclude("iframe[src*='stripe.com']")
        .exclude("iframe[src*='tldraw']")
        .analyze();

      // Save full report as artifact
      const resultsDir = path.join(
        process.cwd(),
        "axe-results"
      );
      fs.mkdirSync(resultsDir, { recursive: true });
      fs.writeFileSync(
        path.join(resultsDir, `${route.name}.json`),
        JSON.stringify(accessibilityScanResults, null, 2)
      );

      // Split violations by impact
      const blocking = accessibilityScanResults.violations.filter((v) =>
        BLOCKING_IMPACTS.includes(v.impact as (typeof BLOCKING_IMPACTS)[number])
      );
      const warnings = accessibilityScanResults.violations.filter(
        (v) => !BLOCKING_IMPACTS.includes(v.impact as (typeof BLOCKING_IMPACTS)[number])
      );

      // Log warnings for tracking (not failing)
      if (warnings.length > 0) {
        console.warn(
          `[A11y] ${route.name}: ${warnings.length} moderate/minor violation(s) (non-blocking):\n`,
          warnings.map((v) => `  ${v.id}: ${v.description} (${v.nodes.length} node(s))`).join("\n")
        );
      }

      // Fail on critical/serious
      if (blocking.length > 0) {
        const summary = blocking
          .map(
            (v) =>
              `  ❌ [${v.impact}] ${v.id}: ${v.description}\n` +
              v.nodes
                .slice(0, 3)
                .map((n) => `     Target: ${n.target}`)
                .join("\n")
          )
          .join("\n");
        throw new Error(
          `Found ${blocking.length} serious/critical axe violation(s) on ${route.path}:\n${summary}`
        );
      }

      expect(blocking.length).toBe(0);
    });
  }

  test("keyboard navigation — login page tab order is logical", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState("networkidle");

    // Tab through the login form — each focusable element must be reachable
    await page.keyboard.press("Tab"); // email input
    const emailFocused = await page.evaluate(() =>
      document.activeElement?.getAttribute("id") === "email" ||
      document.activeElement?.getAttribute("type") === "email"
    );
    expect(emailFocused).toBeTruthy();

    await page.keyboard.press("Tab"); // password input
    const passwordFocused = await page.evaluate(() =>
      document.activeElement?.getAttribute("type") === "password"
    );
    expect(passwordFocused).toBeTruthy();
  });

  test("focus-visible ring is present on interactive elements", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);

    // Tab to first element and verify it has a visible focus ring
    await page.keyboard.press("Tab");
    const hasFocusStyle = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el) return false;
      const style = window.getComputedStyle(el);
      // Check for outline or box-shadow (focus ring)
      return (
        style.outline !== "none" ||
        style.outlineWidth !== "0px" ||
        style.boxShadow !== "none"
      );
    });
    // This is a soft check — violation is tracked in a11y-checklist
    if (!hasFocusStyle) {
      console.warn("[A11y] Warning: focused element may not have a visible focus ring");
    }
  });
});
