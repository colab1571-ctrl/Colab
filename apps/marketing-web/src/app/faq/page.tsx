import type { Metadata } from "next";
import Script from "next/script";
import { BRAND_NAME, SITE_URL } from "../../lib/brand";
import { FaqSearch } from "../../components/FaqSearch";
import { faqItems } from "./data";

export const metadata: Metadata = {
  title: `FAQ — ${BRAND_NAME}`,
  description: `Frequently asked questions about ${BRAND_NAME} — the AI-powered creative collaboration platform.`,
  alternates: { canonical: `${SITE_URL}/faq` },
  openGraph: {
    title: `FAQ — ${BRAND_NAME}`,
    description: "Common questions about the platform, pricing, privacy, and how matching works.",
    url: `${SITE_URL}/faq`,
    images: [{ url: "/og/faq.png", width: 1200, height: 630 }],
  },
};

const faqSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: faqItems.map(({ question, answer }) => ({
    "@type": "Question",
    name: question,
    acceptedAnswer: {
      "@type": "Answer",
      text: answer,
    },
  })),
};

export default function FaqPage(): React.ReactElement {
  return (
    <>
      <Script
        id="ld-json-faq"
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }}
      />

      <section className="max-w-4xl mx-auto px-6 py-16 text-center">
        <h1 className="text-5xl font-bold text-neutral-900 mb-4">
          Frequently asked questions
        </h1>
        <p className="text-xl text-neutral-500 max-w-xl mx-auto">
          Everything you need to know about {BRAND_NAME}.
        </p>
      </section>

      <section className="max-w-3xl mx-auto px-6 pb-24">
        <FaqSearch items={faqItems} />
      </section>
    </>
  );
}
