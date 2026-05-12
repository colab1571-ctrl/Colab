/**
 * packages/i18n/src/init-rn.ts
 *
 * React Native (Expo) i18n initialisation.
 *
 * Stack:
 *   i18n-js v4              – lightweight RN-safe i18n, bundled pluralisation
 *   react-native-localize   – native locale/region detection + change listener
 *
 * Priority chain:
 *   1. User-saved preference  (AsyncStorage key "colab_locale", synced from profile-svc)
 *   2. Device locale          (react-native-localize.findBestAvailableLanguage)
 *   3. Fallback               "en"
 *
 * Usage:
 *   import { i18n, setUserLocale } from "@colab/i18n/src/init-rn";
 *   import { useTranslation } from "./useTranslationRN";
 *
 * RTL:
 *   I18nManager.allowRTL(true)  is set so that adding an RTL locale later requires no layout work.
 *   I18nManager.forceRTL(false) keeps the current LTR layout for the en-only launch.
 */

import { I18n } from "i18n-js";
import * as RNLocalize from "react-native-localize";
import { I18nManager } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

// --- Locale catalog imports (all namespaces, bundled for offline support) ---
import commonEn from "../locales/en/common.json";
import authEn from "../locales/en/auth.json";
import profileEn from "../locales/en/profile.json";
import discoveryEn from "../locales/en/discovery.json";
import inviteEn from "../locales/en/invite.json";
import collabEn from "../locales/en/collab.json";
import chatEn from "../locales/en/chat.json";
import billingEn from "../locales/en/billing.json";
import supportEn from "../locales/en/support.json";
import notificationsEn from "../locales/en/notifications.json";
import moderationEn from "../locales/en/moderation.json";
import adminEn from "../locales/en/admin.json";
import errorsEn from "../locales/en/errors.json";

// ---------------------------------------------------------------------------

export const SUPPORTED_LOCALES = ["en"] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

const LOCALE_STORAGE_KEY = "colab_locale";

// Merge all namespaces under each locale key so i18n.t("common.loading") works
const translations: Record<string, Record<string, unknown>> = {
  en: {
    common: commonEn,
    auth: authEn,
    profile: profileEn,
    discovery: discoveryEn,
    invite: inviteEn,
    collab: collabEn,
    chat: chatEn,
    billing: billingEn,
    support: supportEn,
    notifications: notificationsEn,
    moderation: moderationEn,
    admin: adminEn,
    errors: errorsEn,
  },
};

export const i18n = new I18n(translations);

// --- Defaults ---
i18n.enableFallback = true;
i18n.defaultLocale = "en";

// --- RTL readiness (no RTL locale at launch but infra is ready) ---
I18nManager.allowRTL(true);
I18nManager.forceRTL(false);

// --- Initial locale from device ---
function resolveDeviceLocale(): SupportedLocale {
  // react-native-localize v3 uses findBestLanguageTag (renamed from findBestAvailableLanguage)
  const findFn =
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (RNLocalize as any).findBestLanguageTag ?? (RNLocalize as any).findBestAvailableLanguage;
  const best = findFn?.(SUPPORTED_LOCALES as unknown as string[]);
  return (best?.languageTag as SupportedLocale | undefined) ?? "en";
}

i18n.locale = resolveDeviceLocale();

// --- Apply user-saved preference (async; fires after initial render) ---
AsyncStorage.getItem(LOCALE_STORAGE_KEY).then((saved) => {
  if (saved && (SUPPORTED_LOCALES as readonly string[]).includes(saved)) {
    i18n.locale = saved as SupportedLocale;
  }
});

// --- Update on device locale change (user changes language in iOS/Android settings) ---
// react-native-localize v3 removed addEventListener; use useLocalize hook in components instead.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const addLocalizeListener = (RNLocalize as any).addEventListener;
if (typeof addLocalizeListener === "function") {
  addLocalizeListener("change", () => {
    // Respect saved user preference over device locale if set
    AsyncStorage.getItem(LOCALE_STORAGE_KEY).then((saved) => {
      if (saved && (SUPPORTED_LOCALES as readonly string[]).includes(saved)) {
        i18n.locale = saved as SupportedLocale;
      } else {
        i18n.locale = resolveDeviceLocale();
      }
    });
  });
}

/**
 * Persist user locale selection and update i18n.locale immediately.
 * Should be called from the Settings screen "Language" picker.
 * Also fires an API call to persist to profile-svc (caller's responsibility).
 */
export async function setUserLocale(locale: SupportedLocale): Promise<void> {
  await AsyncStorage.setItem(LOCALE_STORAGE_KEY, locale);
  i18n.locale = locale;
}

/**
 * Shorthand translation helper (use inside non-hook contexts).
 * For React components, prefer the useTranslationRN hook.
 */
export function t(
  scope: string,
  options?: Record<string, string | number | boolean>
): string {
  return i18n.t(scope, options);
}

export default i18n;
