import type { Metadata } from "next";
import { BRAND_NAME, SITE_URL } from "../../lib/brand";

/**
 * Blog index — "Coming soon" stub.
 * noindex to prevent thin-content indexing until blog ships in v1.1.
 */
export const metadata: Metadata = {
  title: "Blog",
  description: `${BRAND_NAME} blog — stories, tips, and news for artists and creators. Coming soon.`,
  alternates: { canonical: `${SITE_URL}/blog` },
  robots: { index: false, follow: false },
};

export default function BlogIndexPage(): React.ReactElement {
  return (
    <section className="max-w-3xl mx-auto px-6 py-32 text-center">
      <p
        className="text-sm font-semibold uppercase tracking-widest mb-4"
        style={{ color: "var(--color-brand-primary)" }}
      >
        Coming soon
      </p>
      <h1 className="text-4xl font-bold text-neutral-900 mb-4">
        The {BRAND_NAME} Blog
      </h1>
      <p className="text-lg text-neutral-500 max-w-xl mx-auto">
        Stories, tips, and news for artists and creators. We&apos;re writing — check back soon.
      </p>
    </section>
  );
}
