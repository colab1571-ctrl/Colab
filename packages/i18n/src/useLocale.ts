/**
 * packages/i18n/src/useLocale.ts
 *
 * Locale switcher utility hook — works on Web (react-i18next) and is
 * re-exported for RN (where callers use setUserLocale from init-rn.ts).
 *
 * Web usage:
 *   const { locale, setLocale } = useLocale();
 *
 * RN usage:
 *   import { setUserLocale } from "@colab/i18n/src/init-rn";
 */

"use client";

import { useTranslation } from "react-i18next";
import { setUserLocale, SUPPORTED_LOCALES, type SupportedLocale } from "./init";

export function useLocale(): {
  locale: SupportedLocale;
  setLocale: (locale: SupportedLocale) => Promise<void>;
  supportedLocales: readonly SupportedLocale[];
} {
  const { i18n } = useTranslation();

  return {
    locale: (i18n.language as SupportedLocale) ?? "en",
    setLocale: setUserLocale,
    supportedLocales: SUPPORTED_LOCALES,
  };
}
