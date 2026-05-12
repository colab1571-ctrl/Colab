/**
 * apps/marketing-web/e2e/a11y/axe.spec.ts
 *
 * axe-core + Playwright accessibility tests for marketing-web.
 */

import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3001";
const BLOCKING_IMPACTS = ["critical", "serious"] as const;

const ROUTES = [
  { path: "/", name: "home" },
  { path: "/pricing", name: "pricing" },
  { path: "/how-it-works", name: "how-it-works" },
  { path: "/faq", name: "faq" },
  { path: "/about", name: "about" },
  { path: "/blog", name: "blog" },
  { path: "/legal/tos", name: "tos" },
  { path: "/legal/privacy", name: "privacy" },
  { path: "/legal/community-guidelines", name: "community-guidelines" },
];

test.describe("axe-core accessibility — marketing-web", () => {
  for (const route of ROUTES) {
    test(`${route.name} (${route.path}) — zero critical/serious violations`, async ({ page }) => {
      await page.goto(`${BASE_URL}${route.path}`);
      await page.waitForLoadState("networkidle");

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      const resultsDir = path.join(process.cwd(), "axe-results");
      fs.mkdirSync(resultsDir, { recursive: true });
      fs.writeFileSync(
        path.join(resultsDir, `${route.name}.json`),
        JSON.stringify(results, null, 2)
      );

      const blocking = results.violations.filter((v) =>
        BLOCKING_IMPACTS.includes(v.impact as (typeof BLOCKING_IMPACTS)[number])
      );

      const warnings = results.violations.filter(
        (v) => !BLOCKING_IMPACTS.includes(v.impact as (typeof BLOCKING_IMPACTS)[number])
      );

      if (warnings.length > 0) {
        console.warn(
          `[A11y] marketing-web/${route.name}: ${warnings.length} non-blocking violation(s):\n`,
          warnings.map((v) => `  ${v.id}: ${v.description}`).join("\n")
        );
      }

      if (blocking.length > 0) {
        throw new Error(
          `${blocking.length} serious/critical violation(s) on ${route.path}:\n` +
            blocking.map((v) => `  [${v.impact}] ${v.id}: ${v.description}`).join("\n")
        );
      }

      expect(blocking.length).toBe(0);
    });
  }

  test("waitlist form — keyboard accessible and labeled", async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await page.waitForLoadState("networkidle");

    // The waitlist form email input must be labelled
    const emailInput = page.getByRole("textbox", { name: /email/i });
    await expect(emailInput).toBeVisible();

    // Submit button must be labelled
    const submitBtn = page.getByRole("button", { name: /join waitlist/i });
    await expect(submitBtn).toBeVisible();

    // Tab navigation reaches the form
    await page.keyboard.press("Tab");
    // Keep tabbing until we reach the email input
    let found = false;
    for (let i = 0; i < 20; i++) {
      const active = await page.evaluate(() => document.activeElement?.getAttribute("type"));
      if (active === "email") { found = true; break; }
      await page.keyboard.press("Tab");
    }
    expect(found).toBeTruthy();
  });
});
