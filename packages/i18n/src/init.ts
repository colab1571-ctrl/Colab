/**
 * packages/i18n/src/init.ts
 *
 * Web (Next.js) i18next initialisation.
 *
 * Stack:
 *   i18next            – core engine
 *   react-i18next v15  – React hooks + provider
 *   i18next-icu        – ICU MessageFormat (plurals, gender, select)
 *   i18next-http-backend  – lazy-load locale JSON at runtime
 *   i18next-browser-languagedetector – auto-detect from querystring / localStorage / navigator
 *
 * Priority chain: user preference (localStorage "colab_locale") → device locale → "en"
 *
 * Usage:
 *   import "@colab/i18n/src/init";   // in app entry point (_app.tsx / layout.tsx)
 *   import { useTranslation } from "react-i18next";
 */

import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import ICU from "i18next-icu";
import HttpBackend from "i18next-http-backend";
import LanguageDetector from "i18next-browser-languagedetector";

import type { Namespace } from "./types";

export const SUPPORTED_LOCALES = ["en"] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

export const ALL_NAMESPACES: Namespace[] = [
  "common",
  "auth",
  "profile",
  "discovery",
  "invite",
  "collab",
  "chat",
  "billing",
  "support",
  "notifications",
  "moderation",
  "admin",
  "errors",
];

const USER_PREF_KEY = "colab_locale";

/**
 * Resolve locale preference stored by the settings screen.
 * Returns null when no preference is saved.
 */
function getStoredLocale(): SupportedLocale | null {
  if (typeof localStorage === "undefined") return null;
  const stored = localStorage.getItem(USER_PREF_KEY);
  if (stored && (SUPPORTED_LOCALES as readonly string[]).includes(stored)) {
    return stored as SupportedLocale;
  }
  return null;
}

/**
 * Persist user locale preference.
 * Called from the settings "Language" picker.
 */
export async function setUserLocale(locale: SupportedLocale): Promise<void> {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(USER_PREF_KEY, locale);
  }
  await i18next.changeLanguage(locale);
}

if (!i18next.isInitialized) {
  i18next
    .use(ICU)
    .use(HttpBackend)
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
      fallbackLng: "en",
      supportedLngs: SUPPORTED_LOCALES,
      ns: ["common"],
      defaultNS: "common",
      backend: {
        loadPath: "/locales/{{lng}}/{{ns}}.json",
      },
      detection: {
        // User-saved preference wins; then browser language; then html lang attr
        order: ["localStorage", "navigator", "htmlTag"],
        lookupLocalStorage: USER_PREF_KEY,
        caches: ["localStorage"],
      },
      interpolation: {
        escapeValue: false, // React already escapes
      },
      react: {
        useSuspense: false, // safer for SSR / streaming
      },
      // Override detection result with persisted user pref (step 1 of priority chain)
      ...(getStoredLocale() != null ? { lng: getStoredLocale() as string } : {}),
    });
}

export default i18next;
