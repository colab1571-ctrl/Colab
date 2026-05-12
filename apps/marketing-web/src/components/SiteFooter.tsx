import Link from "next/link";
import { BRAND_NAME } from "../lib/brand";
import { AppStoreBadges } from "./AppStoreBadges";

const legalLinks = [
  { href: "/legal/tos", label: "Terms of Service" },
  { href: "/legal/privacy", label: "Privacy Policy" },
  { href: "/legal/community-guidelines", label: "Community Guidelines" },
  { href: "/legal/dmca", label: "DMCA" },
  { href: "/legal/cookies", label: "Cookie Policy" },
];

const siteLinks = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/faq", label: "FAQ" },
  { href: "/about", label: "About" },
  { href: "/blog", label: "Blog" },
];

export function SiteFooter(): React.ReactElement {
  const year = new Date().getFullYear();
  return (
    <footer className="bg-neutral-900 text-neutral-400 mt-24">
      <div className="max-w-6xl mx-auto px-6 py-16">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-12 mb-12">
          {/* Brand */}
          <div>
            <p
              className="text-xl font-bold mb-3"
              style={{ color: "var(--color-brand-primary)" }}
            >
              {BRAND_NAME}
            </p>
            <p className="text-sm leading-relaxed">
              AI-powered collaboration for artists and creators.
              <br />
              US · CA · AU · NZ · IN · 18+ only
            </p>
            <div className="mt-6">
              <AppStoreBadges />
            </div>
          </div>

          {/* Site links */}
          <nav aria-label="Site links">
            <p className="text-xs uppercase tracking-widest text-neutral-500 mb-4 font-semibold">
              Site
            </p>
            <ul className="space-y-2 list-none m-0 p-0">
              {siteLinks.map(({ href, label }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="text-sm hover:text-neutral-100 transition-colors"
                  >
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          {/* Legal links */}
          <nav aria-label="Legal links">
            <p className="text-xs uppercase tracking-widest text-neutral-500 mb-4 font-semibold">
              Legal
            </p>
            <ul className="space-y-2 list-none m-0 p-0">
              {legalLinks.map(({ href, label }) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="text-sm hover:text-neutral-100 transition-colors"
                  >
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        <div className="border-t border-neutral-800 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-xs">
            &copy; {year} {BRAND_NAME}. All rights reserved.
          </p>
          <p className="text-xs">
            Made for artists, by artists.
          </p>
        </div>
      </div>
    </footer>
  );
}
