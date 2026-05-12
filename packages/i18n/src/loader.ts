/**
 * i18n loader utility — works on both React Native and web.
 *
 * Usage (RN + i18next):
 *   import { initI18n } from "@colab/i18n/loader";
 *   await initI18n({ locale: "en" });
 *
 * Usage (Next.js, server-side):
 *   import { getTranslations } from "@colab/i18n/loader";
 *   const t = getTranslations("en", "auth");
 *   t("sign_in") // → "Sign In"
 */

export type Namespace =
  | "common"
  | "auth"
  | "profile"
  | "discovery"
  | "invite"
  | "collab"
  | "chat"
  | "billing"
  | "support"
  | "notifications"
  | "moderation"
  | "admin"
  | "errors";

export type Locale = "en";

export const SUPPORTED_LOCALES: Locale[] = ["en"];
export const DEFAULT_LOCALE: Locale = "en";
export const NAMESPACES: Namespace[] = [
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

// ---------------------------------------------------------------------------
// Simple synchronous loader (static imports for bundler tree-shaking)
// ---------------------------------------------------------------------------

const catalogs: Record<Locale, Record<Namespace, Record<string, string>>> = {
  en: {
    common: {} as Record<string, string>,
    auth: {} as Record<string, string>,
    profile: {} as Record<string, string>,
    discovery: {} as Record<string, string>,
    invite: {} as Record<string, string>,
    collab: {} as Record<string, string>,
    chat: {} as Record<string, string>,
    billing: {} as Record<string, string>,
    support: {} as Record<string, string>,
    notifications: {} as Record<string, string>,
    moderation: {} as Record<string, string>,
    admin: {} as Record<string, string>,
    errors: {} as Record<string, string>,
  },
};

/**
 * Register translations at runtime (used by bundler-specific loaders).
 */
export function registerCatalog(
  locale: Locale,
  ns: Namespace,
  messages: Record<string, string>
): void {
  catalogs[locale][ns] = { ...catalogs[locale][ns], ...messages };
}

/**
 * Get a typed translation function for a namespace.
 * Simple interpolation: {{key}} placeholders are replaced with values.
 */
export function getTranslations(
  locale: Locale,
  ns: Namespace
): (key: string, vars?: Record<string, string | number>) => string {
  const messages = catalogs[locale]?.[ns] ?? {};
  return (key: string, vars?: Record<string, string | number>) => {
    let str = messages[key] ?? key;
    if (vars) {
      for (const [k, v] of Object.entries(vars)) {
        str = str.replaceAll(`{{${k}}}`, String(v));
      }
    }
    return str;
  };
}

/**
 * i18next-compatible resource bundles for use with i18next init.
 * Returns an object shaped as { [locale]: { [ns]: { [key]: value } } }.
 */
export function getI18nResources(locale: Locale = DEFAULT_LOCALE): Record<string, unknown> {
  return { [locale]: catalogs[locale] };
}
