/**
 * Brand constants — all copy that references the brand name flows through here.
 * Replace BRAND_NAME before launch (Phase 5 design pass).
 * Driven by NEXT_PUBLIC_BRAND_NAME env var at build time.
 */

export const BRAND_NAME =
  process.env.NEXT_PUBLIC_BRAND_NAME ?? "<BRAND_NAME>";

export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://colabclub.net";

export const APP_STORE_URL =
  process.env.NEXT_PUBLIC_APP_STORE_URL ?? "";

export const PLAY_STORE_URL =
  process.env.NEXT_PUBLIC_PLAY_STORE_URL ?? "";

export const POSTHOG_KEY =
  process.env.NEXT_PUBLIC_POSTHOG_KEY ?? "";

export const POSTHOG_HOST =
  process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://app.posthog.com";

/** Social links — populated before launch */
export const SOCIAL_LINKS = {
  instagram: process.env.NEXT_PUBLIC_INSTAGRAM_URL ?? "",
  twitter: process.env.NEXT_PUBLIC_TWITTER_URL ?? "",
};
