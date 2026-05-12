import type { Metadata } from "next";
import { notFound } from "next/navigation";

/**
 * Blog post route — reserved for v1.1.
 * Returns a static 404 shell until blog content ships.
 * noindex to prevent indexing of empty stubs.
 *
 * generateStaticParams returns an empty array so no pages are pre-rendered
 * at build time, and the route correctly 404s for any slug at runtime.
 */
export const metadata: Metadata = {
  title: "Post not found",
  robots: { index: false, follow: false },
};

export function generateStaticParams(): Array<{ slug: string }> {
  // No blog posts yet — blog ships in v1.1
  return [];
}

export default function BlogPostPage(): never {
  notFound();
}
