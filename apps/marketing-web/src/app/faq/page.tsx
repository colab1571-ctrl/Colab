import type { Metadata } from "next";
import Script from "next/script";
import { BRAND_NAME, SITE_URL } from "../../lib/brand";
import { FaqSearch } from "../../components/FaqSearch";

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

export interface FaqItem {
  question: string;
  answer: string;
}

export const faqItems: FaqItem[] = [
  {
    question: "Is it free?",
    answer: `${BRAND_NAME} offers a free tier that includes 30 profile views per day and 5 Vibe Checks per week. Premium plans unlock unlimited connections, AI credits, chat export, and more.`,
  },
  {
    question: "What types of creators can join?",
    answer:
      "Artists and creators across 9 vocation categories: visual arts, music, design, film/video, writing/content, dance/performance, digital art, craft/textile, and other. Minimum age 18.",
  },
  {
    question: "How does the AI matching work?",
    answer:
      `The matching engine generates embeddings from your portfolio and profile, then surfaces creators with complementary skills and compatible creative vision. Ranking factors include portfolio similarity (40%), complementary vocations (25%), recent activity (15%), and profile health (10%). Weights are admin-configurable.`,
  },
  {
    question: "Is my creative work safe on the platform?",
    answer:
      "All files shared in workspaces are version-tracked with immutable audit logs. AI tools (like AI Collab Preview) require mutual consent from both collaborators before activation. You can export your chat and files at any time.",
  },
  {
    question: "What happens if I send a Vibe Check and the other person doesn't respond?",
    answer:
      "Unanswered Vibe Checks expire automatically after 30 days and move to your 'past requests sent' history. The recipient is not notified of the expiry.",
  },
  {
    question: "Can I collaborate with people outside my country?",
    answer:
      "Yes. Each profile has an 'open to remote' toggle. You can also set your collaboration radius to 'Anywhere' when browsing.",
  },
  {
    question: "Which countries can sign up?",
    answer: `At launch: United States, Canada, Australia, New Zealand, and India. EU and UK are not available at launch.`,
  },
  {
    question: "What is the minimum age?",
    answer: "18 years old. Age is enforced via Terms of Service attestation at signup, and Persona identity verification cross-checks face age signals for manual review.",
  },
  {
    question: "How do I report inappropriate content or behaviour?",
    answer:
      "Every chat and profile has a Report button that routes directly to our moderation team. We have a tiered response system with SLAs ranging from 1 hour (severe) to 7 days (general).",
  },
  {
    question: "What data do you collect?",
    answer: `See our Privacy Policy for full details. At a high level: account data (email, profile), portfolio content, collaboration activity, and usage analytics (PostHog). We do not sell your data or run ads at launch.`,
  },
  {
    question: "Does the platform have ads?",
    answer: `No ads at launch. Free users may see ads in a future update. Premium users can toggle ads off.`,
  },
  {
    question: "How do I cancel my subscription?",
    answer:
      "You can cancel any time from your account settings. Mobile subscriptions are managed through Apple or Google. A 14-day no-questions refund is available for web subscriptions.",
  },
  {
    question: `When does ${BRAND_NAME} launch?`,
    answer:
      `We're in pre-launch. Join the waitlist and we'll email you when we open access.`,
  },
];

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
