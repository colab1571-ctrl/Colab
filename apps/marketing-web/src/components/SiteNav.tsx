import Link from "next/link";
import { BRAND_NAME } from "../lib/brand";

export function SiteNav(): React.ReactElement {
  return (
    <header className="sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-neutral-100">
      <nav
        className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between"
        aria-label="Main navigation"
      >
        <Link
          href="/"
          className="text-xl font-bold"
          style={{ color: "var(--color-brand-primary)" }}
          aria-label={`${BRAND_NAME} home`}
        >
          {BRAND_NAME}
        </Link>

        <ul className="hidden md:flex items-center gap-6 list-none m-0 p-0">
          <li>
            <Link
              href="/how-it-works"
              className="text-sm text-neutral-600 hover:text-neutral-900 transition-colors"
            >
              How it works
            </Link>
          </li>
          <li>
            <Link
              href="/faq"
              className="text-sm text-neutral-600 hover:text-neutral-900 transition-colors"
            >
              FAQ
            </Link>
          </li>
          <li>
            <Link
              href="/about"
              className="text-sm text-neutral-600 hover:text-neutral-900 transition-colors"
            >
              About
            </Link>
          </li>
        </ul>

        <a
          href="#waitlist"
          className="btn-primary text-sm py-2 px-5"
        >
          Join waitlist
        </a>
      </nav>
    </header>
  );
}
