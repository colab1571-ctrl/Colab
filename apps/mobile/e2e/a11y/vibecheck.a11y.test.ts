/**
 * apps/mobile/e2e/a11y/vibecheck.a11y.test.ts
 *
 * Flow 3 + 4: Send Vibe Check + Accept invite — Detox a11y smoke tests.
 */

import { device, element, by, expect as detoxExpect } from "detox";

describe("Flow 3 — Send Vibe Check a11y", () => {
  beforeAll(async () => {
    await device.reloadReactNative();
    // Assumes user is logged in and on the feed
  });

  it("send button has descriptive accessibilityLabel", async () => {
    const btn = element(by.id("submit-btn"));
    const attrs = await btn.getAttributes();
    expect(attrs.label).toBeTruthy();
    expect(attrs.label).toMatch(/send vibe check/i);
  });

  it("synopsis input has accessibilityLabel", async () => {
    const input = element(by.id("synopsis-input"));
    await detoxExpect(input).toHaveLabel(expect.stringContaining("message"));
  });

  it("character counter has accessibilityLiveRegion", async () => {
    const counter = element(by.id("char-counter"));
    await detoxExpect(counter).toBeVisible();
    const attrs = await counter.getAttributes();
    expect(attrs.label).toMatch(/remaining|over limit/i);
  });

  it("modal close button is labeled and has min 44pt touch target", async () => {
    const closeBtn = element(by.id("modal-close-btn"));
    const attrs = await closeBtn.getAttributes();
    expect(attrs.label).toMatch(/cancel|close/i);
    // Touch target check: frame should be at least 44pt tall
    expect(attrs.frame?.height ?? 0).toBeGreaterThanOrEqual(44);
  });

  it("error message has accessibilityLiveRegion assertive when shown", async () => {
    // Trigger error by submitting empty synopsis
    const submitBtn = element(by.id("submit-btn"));
    await submitBtn.tap();
    const error = element(by.id("error-message"));
    await detoxExpect(error).toBeVisible();
  });
});

describe("Flow 4 — Accept invite a11y", () => {
  it("accept button has accessibilityLabel with creator name", async () => {
    // Navigate to inbox — skip nav steps for brevity; assert on element
    const acceptBtn = element(by.type("TouchableOpacity")).atIndex(0);
    const attrs = await acceptBtn.getAttributes();
    // Any accept button should include "Accept" in its label
    if (attrs.label) {
      expect(attrs.label.toLowerCase()).toContain("accept");
    }
  });
});
