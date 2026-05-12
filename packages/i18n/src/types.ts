/**
 * packages/i18n/src/types.ts
 *
 * Shared TypeScript types for the @colab/i18n package.
 * All apps import from here to keep namespace/locale types in sync.
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

/** i18next resource bundle shape used during SSR init */
export type I18nResources = Record<Locale, Record<Namespace, Record<string, unknown>>>;

/** Return type of the useTranslation hook's t() function */
export type TFunction = (key: string, options?: Record<string, string | number | boolean | null>) => string;
