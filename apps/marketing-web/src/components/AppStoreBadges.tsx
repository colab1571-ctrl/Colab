import { APP_STORE_URL, PLAY_STORE_URL, BRAND_NAME } from "../lib/brand";

/**
 * App Store + Play Store badges.
 * Hidden when env vars are empty (pre-store-submission).
 * Links open in new tab with noopener noreferrer.
 */
export function AppStoreBadges({
  className = "",
}: {
  className?: string;
}): React.ReactElement | null {
  const hasAppStore = Boolean(APP_STORE_URL);
  const hasPlayStore = Boolean(PLAY_STORE_URL);

  if (!hasAppStore && !hasPlayStore) return null;

  return (
    <div className={`flex flex-wrap gap-3 items-center ${className}`}>
      {hasAppStore && (
        <a
          href={APP_STORE_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Download ${BRAND_NAME} on the App Store`}
          className="inline-flex items-center gap-2 bg-black text-white text-sm font-semibold px-4 py-2.5 rounded-xl hover:bg-neutral-800 transition-colors"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98l-.09.06c-.22.14-2.19 1.28-2.17 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.77M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
          </svg>
          <span>
            <span className="text-xs block leading-none opacity-80">
              Download on the
            </span>
            App Store
          </span>
        </a>
      )}

      {hasPlayStore && (
        <a
          href={PLAY_STORE_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Get ${BRAND_NAME} on Google Play`}
          className="inline-flex items-center gap-2 bg-black text-white text-sm font-semibold px-4 py-2.5 rounded-xl hover:bg-neutral-800 transition-colors"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M3 20.5v-17c0-.83.94-1.3 1.6-.8l14 8.5c.6.36.6 1.24 0 1.6l-14 8.5c-.66.5-1.6.03-1.6-.8z" />
          </svg>
          <span>
            <span className="text-xs block leading-none opacity-80">
              Get it on
            </span>
            Google Play
          </span>
        </a>
      )}
    </div>
  );
}
