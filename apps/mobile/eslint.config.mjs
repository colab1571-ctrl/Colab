/**
 * apps/mobile/eslint.config.mjs
 *
 * ESLint flat config for the React Native / Expo mobile app.
 * Adds eslint-plugin-react-native-a11y for WCAG 2.1 AA enforcement on RN.
 */

import js from "@eslint/js";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import rnA11y from "eslint-plugin-react-native-a11y";

export default [
  js.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
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
      "react-native-a11y": rnA11y,
    },
    rules: {
      // TypeScript recommended
      ...tsPlugin.configs.recommended.rules,

      // React Native accessibility — all rules enabled
      ...rnA11y.configs.all.rules,

      // Allow 'no-unsafe-*' rules as warnings for now (avoid blocking CI on third-party code)
      "@typescript-eslint/no-unsafe-assignment": "warn",
      "@typescript-eslint/no-unsafe-member-access": "warn",
      "@typescript-eslint/no-unsafe-call": "warn",
      "@typescript-eslint/no-explicit-any": "warn",

      // Suppressions for patterns used in existing code
      "react-native-a11y/has-valid-accessibility-ignores-invert-colors": "warn",
    },
  },
  {
    ignores: ["node_modules/**", ".expo/**", "dist/**"],
  },
];
