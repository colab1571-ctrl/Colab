/**
 * packages/ui/src/__tests__/color-contrast.test.ts
 *
 * Design token color-contrast tests.
 *
 * Asserts WCAG 2.1 AA ratios:
 *   - Normal text (< 18pt / < 14pt bold): ≥ 4.5:1
 *   - Large text (≥ 18pt regular, ≥ 14pt bold): ≥ 3:1
 *   - UI components (borders, icons conveying meaning): ≥ 3:1
 *
 * Runs in CI via test.yml. Failure blocks merge.
 *
 * NOTE: Color values are extracted from the design token CSS variables defined
 * in packages/ui/src/theme/. Until the token audit (C-01/C-02) is complete,
 * this file uses placeholder values that WILL be replaced with actual token
 * hex values from the design system. Update this file as part of C-02.
 */

import { describe, test, expect } from "vitest";

// ---------------------------------------------------------------------------
// Minimal WCAG contrast ratio calculator (avoids external dep)
// ---------------------------------------------------------------------------

/** Convert 8-bit sRGB channel to linear light */
function toLinear(val: number): number {
  const c = val / 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** Relative luminance of an sRGB color [0-255, 0-255, 0-255] */
function luminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
}

/** Parse a hex color string (#rrggbb or #rgb) to [r, g, b] */
function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  if (h.length === 3) {
    return [
      parseInt(h[0] + h[0], 16),
      parseInt(h[1] + h[1], 16),
      parseInt(h[2] + h[2], 16),
    ];
  }
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

/** WCAG contrast ratio between two hex colors */
function contrastRatio(fg: string, bg: string): number {
  const l1 = luminance(hexToRgb(fg));
  const l2 = luminance(hexToRgb(bg));
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// ---------------------------------------------------------------------------
// Design token values
// These MUST be updated to match the actual resolved CSS variable values
// from packages/ui/src/theme/ before C-02 is considered complete.
// ---------------------------------------------------------------------------

/**
 * Token color map — hex values resolved from CSS custom properties.
 * Format: { tokenName: hexColor }
 *
 * TODO (C-01/C-02): Replace placeholder values with actual token hex values
 * extracted via the design-token generation pipeline.
 */
const COLORS = {
  // Text
  "text.primary": "#1A1A1A",      // --color-foreground (dark on white)
  "text.secondary": "#6B7280",    // --color-muted-foreground
  "text.on_primary": "#FFFFFF",   // white text on brand primary button

  // Surfaces
  "surface.default": "#FFFFFF",   // default page background
  "surface.muted": "#F9FAFB",     // muted surface

  // Brand
  "brand.primary": "#5B5BD6",     // --color-brand-primary (indigo)
  "brand.secondary": "#7C3AED",   // --color-brand-secondary

  // Borders / UI
  "border.default": "#E5E7EB",    // --color-border
  "border.focus": "#5B5BD6",      // focus ring (brand primary)
  "icon.secondary": "#6B7280",    // secondary icon color

  // Status
  "status.error": "#DC2626",      // red-600
  "status.success": "#16A34A",    // green-600
  "status.warning": "#D97706",    // amber-600
} as const;

type ColorToken = keyof typeof COLORS;

// ---------------------------------------------------------------------------
// Test matrices
// ---------------------------------------------------------------------------

/** Text pairs — must achieve ≥ 4.5:1 (normal text) */
const TEXT_PAIRS: Array<{ fg: ColorToken; bg: ColorToken; description: string }> = [
  { fg: "text.primary", bg: "surface.default", description: "Primary text on white background" },
  { fg: "text.secondary", bg: "surface.default", description: "Secondary text on white background" },
  { fg: "text.secondary", bg: "surface.muted", description: "Secondary text on muted surface" },
  { fg: "text.on_primary", bg: "brand.primary", description: "White text on brand primary button" },
  { fg: "status.error", bg: "surface.default", description: "Error text on white" },
  { fg: "status.success", bg: "surface.default", description: "Success text on white" },
];

/** UI component pairs — must achieve ≥ 3:1 (borders, icons, focus rings) */
const UI_PAIRS: Array<{ fg: ColorToken; bg: ColorToken; description: string }> = [
  { fg: "border.focus", bg: "surface.default", description: "Focus ring on white background" },
  { fg: "icon.secondary", bg: "surface.default", description: "Secondary icon on white" },
  { fg: "brand.primary", bg: "surface.default", description: "Brand primary UI element on white" },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Design token color contrast — WCAG 2.1 AA", () => {
  describe("Normal text contrast (≥ 4.5:1)", () => {
    test.each(TEXT_PAIRS)(
      "$description — $fg on $bg",
      ({ fg, bg, description: _ }) => {
        const ratio = contrastRatio(COLORS[fg], COLORS[bg]);
        expect(ratio).toBeGreaterThanOrEqual(4.5);
      }
    );
  });

  describe("UI component contrast (≥ 3:1)", () => {
    test.each(UI_PAIRS)(
      "$description — $fg on $bg",
      ({ fg, bg, description: _ }) => {
        const ratio = contrastRatio(COLORS[fg], COLORS[bg]);
        expect(ratio).toBeGreaterThanOrEqual(3.0);
      }
    );
  });

  test("contrast ratio calculator is correct (known pair)", () => {
    // Black on white = 21:1
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 0);
    // White on white = 1:1
    expect(contrastRatio("#FFFFFF", "#FFFFFF")).toBeCloseTo(1, 0);
  });
});
