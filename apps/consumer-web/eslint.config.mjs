/**
 * apps/consumer-web/eslint.config.mjs
 *
 * ESLint flat config for the consumer Next.js app.
 * Adds eslint-plugin-jsx-a11y recommended preset (WCAG 2.1 AA static analysis).
 */

import jsxA11y from "eslint-plugin-jsx-a11y";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import nextPlugin from "@next/eslint-plugin-next";

export default [
  // jsx-a11y recommended flat config
  jsxA11y.flatConfigs.recommended,
  {
    files: ["src/**/*.{ts,tsx}", "app/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      "jsx-a11y": jsxA11y,
      "@next/next": nextPlugin,
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs["core-web-vitals"].rules,

      // Enforce descriptive link text (no "click here", "read more")
      "jsx-a11y/anchor-ambiguous-text": "error",
      // Require aria-label or aria-labelledby on interactive elements
      "jsx-a11y/interactive-supports-focus": "error",
      // No positive tabIndex
      "jsx-a11y/tabindex-no-positive": "error",
      // Media must have captions
      "jsx-a11y/media-has-caption": "warn",
      // Headings must have content
      "jsx-a11y/heading-has-content": "error",
    },
  },
  {
    ignores: ["node_modules/**", ".next/**", "dist/**"],
  },
];
