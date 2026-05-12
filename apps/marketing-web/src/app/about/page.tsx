import type { Metadata } from "next";
import { BRAND_NAME, SITE_URL } from "../../lib/brand";
import { WaitlistForm } from "../../components/WaitlistForm";

export const metadata: Metadata = {
  title: `About ${BRAND_NAME}`,
  description: `Learn about ${BRAND_NAME}'s mission to build the leading AI-powered creative collaboration platform for artists and creators.`,
  alternates: { canonical: `${SITE_URL}/about` },
  openGraph: {
    title: `About ${BRAND_NAME}`,
    description: "Our mission, values, and the team building the future of creative collaboration.",
    url: `${SITE_URL}/about`,
    images: [{ url: "/og/about.png", width: 1200, height: 630 }],
  },
};

const values = [
  {
    title: "Output over metrics",
    description:
      "We measure success by creative output — real projects completed, real partnerships formed. Not time-on-app. Not follower growth.",
  },
  {
    title: "Safety by design",
    description:
      "IP-safe workspaces, mutual-consent AI tools, immutable audit logs. Your creative work is protected from day one.",
  },
  {
    title: "Low friction, high trust",
    description:
      "Every design decision asks: does this help artists create together, or does it get in the way? We remove friction, not relationships.",
  },
  {
    title: "Anti-algorithm",
    description:
      "We don't surface content based on engagement. We surface collaborators based on creative compatibility. Different goal, different platform.",
  },
];

export default function AboutPage(): React.ReactElement {
  return (
    <>
      <section className="max-w-4xl mx-auto px-6 py-16">
        <h1 className="text-5xl font-bold text-neutral-900 mb-6">
          About {BRAND_NAME}
        </h1>
        <p className="text-xl text-neutral-500 leading-relaxed max-w-2xl">
          We&apos;re building the leading AI-powered networking and collaboration
          platform for rising artists and creators in the gig economy.
          Low-friction, anti-engagement-farming, productive-partnerships-first.
        </p>
      </section>

      {/* Mission */}
      <section
        className="bg-neutral-50 py-16 px-6"
        aria-labelledby="mission-heading"
      >
        <div className="max-w-3xl mx-auto">
          <h2
            id="mission-heading"
            className="text-3xl font-bold text-neutral-900 mb-6"
          >
            Our mission
          </h2>
          <p className="text-neutral-600 leading-relaxed text-lg mb-4">
            The internet gave artists a global stage — but filled it with noise.
            Today&apos;s creator platforms optimize for time-on-app and follower
            counts, not for the thing artists actually want: to make something
            meaningful with other talented people.
          </p>
          <p className="text-neutral-600 leading-relaxed text-lg mb-4">
            {BRAND_NAME} is built on one premise: the best creative work happens
            through collaboration. Not through going viral. Not through
            accumulating followers. Through finding the right co-founder and
            building something together.
          </p>
          <p className="text-neutral-600 leading-relaxed text-lg">
            We&apos;re starting with artists and creators — musicians, designers,
            filmmakers, writers, visual artists — and building the platform they
            deserve.
          </p>
        </div>
      </section>

      {/* Values */}
      <section
        className="py-16 px-6"
        aria-labelledby="values-heading"
      >
        <div className="max-w-4xl mx-auto">
          <h2
            id="values-heading"
            className="text-3xl font-bold text-neutral-900 mb-10"
          >
            What we believe
          </h2>
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-8 list-none m-0 p-0">
            {values.map(({ title, description }) => (
              <li key={title} className="p-6 bg-neutral-50 rounded-2xl">
                <h3 className="text-lg font-bold text-neutral-900 mb-2">
                  {title}
                </h3>
                <p className="text-neutral-500 leading-relaxed text-sm">
                  {description}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Team placeholder */}
      <section
        className="bg-neutral-50 py-16 px-6"
        aria-labelledby="team-heading"
      >
        <div className="max-w-4xl mx-auto text-center">
          <h2
            id="team-heading"
            className="text-3xl font-bold text-neutral-900 mb-4"
          >
            The team
          </h2>
          <p className="text-neutral-400 text-sm">
            [Team bios — populated at Phase 5 design pass and launch]
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-6 text-center">
        <div className="max-w-xl mx-auto">
          <h2 className="text-3xl font-bold text-neutral-900 mb-4">
            Be part of the founding community
          </h2>
          <p className="text-neutral-500 mb-8">
            Join the waitlist. We&apos;re launching in the US, CA, AU, NZ, and IN.
          </p>
          <WaitlistForm source="about" />
        </div>
      </section>
    </>
  );
}
