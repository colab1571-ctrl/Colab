/**
 * apps/admin-web/e2e/a11y/axe.spec.ts
 *
 * axe-core + Playwright accessibility tests for admin-web.
 */

import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3002";
const BLOCKING_IMPACTS = ["critical", "serious"] as const;

const ROUTES = [
  { path: "/", name: "root" },
  { path: "/login", name: "login" },
  { path: "/dashboard", name: "dashboard" },
  { path: "/moderation/queue", name: "mod-queue" },
  { path: "/support/queue", name: "support-queue" },
  { path: "/users", name: "users" },
  { path: "/audit", name: "audit" },
  { path: "/flags", name: "feature-flags" },
  { path: "/billing", name: "billing" },
  { path: "/kpis", name: "kpis" },
];

test.describe("axe-core accessibility — admin-web", () => {
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
          `[A11y] admin-web/${route.name}: ${warnings.length} non-blocking violation(s):\n`,
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
});
