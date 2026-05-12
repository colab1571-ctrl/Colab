import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { BRAND_NAME, SITE_URL, SOCIAL_LINKS } from "../lib/brand";
import { SiteNav } from "../components/SiteNav";
import { SiteFooter } from "../components/SiteFooter";
import { CookieBanner } from "../components/CookieBanner";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${BRAND_NAME} — Find Your Creative Co-Founder`,
    template: `%s | ${BRAND_NAME}`,
  },
  description:
    "AI-powered networking and collaboration for artists and creators. No follower counts, no engagement farming — just real creative output.",
  robots: { index: true, follow: true },
  openGraph: {
    siteName: BRAND_NAME,
    type: "website",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
  },
};

const orgSchema = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: BRAND_NAME,
  url: SITE_URL,
  logo: `${SITE_URL}/images/logo.png`,
  sameAs: [SOCIAL_LINKS.instagram, SOCIAL_LINKS.twitter].filter(Boolean),
};

const webSiteSchema = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: BRAND_NAME,
  url: SITE_URL,
  potentialAction: {
    "@type": "SearchAction",
    target: `${SITE_URL}/search?q={search_term_string}`,
    "query-input": "required name=search_term_string",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <html lang="en" className={inter.variable}>
      <head>
        <link rel="preconnect" href="https://app.posthog.com" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="bg-white text-neutral-900 antialiased font-sans">
        <SiteNav />
        <main>{children}</main>
        <SiteFooter />
        <CookieBanner />
        <Script
          id="ld-json-org"
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(orgSchema) }}
        />
        <Script
          id="ld-json-website"
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(webSiteSchema) }}
        />
      </body>
    </html>
  );
}
