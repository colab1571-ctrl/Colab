import Link from "next/link";

interface MDXLayoutProps {
  children: React.ReactNode;
  title: string;
  lastUpdated?: string;
}

/**
 * Shared wrapper for MDX legal and content pages.
 * Renders consistent header, breadcrumb, and prose container.
 */
export function MDXLayout({
  children,
  title,
  lastUpdated,
}: MDXLayoutProps): React.ReactElement {
  return (
    <div className="max-w-3xl mx-auto px-6 py-16">
      {/* Breadcrumb */}
      <nav aria-label="Breadcrumb" className="mb-8">
        <ol className="flex items-center gap-2 text-sm text-neutral-500 list-none m-0 p-0">
          <li>
            <Link href="/" className="hover:text-neutral-900 transition-colors">
              Home
            </Link>
          </li>
          <li aria-hidden="true">/</li>
          <li className="text-neutral-900 font-medium" aria-current="page">
            {title}
          </li>
        </ol>
      </nav>

      <article className="prose prose-neutral max-w-none prose-headings:font-bold prose-a:text-[var(--color-brand-primary)] prose-a:no-underline hover:prose-a:underline">
        <h1>{title}</h1>
        {lastUpdated && (
          <p className="text-sm text-neutral-500 not-prose mb-8">
            Last updated:{" "}
            <time dateTime={lastUpdated}>
              {new Date(lastUpdated).toLocaleDateString("en-US", {
                year: "numeric",
                month: "long",
                day: "numeric",
              })}
            </time>
          </p>
        )}
        {children}
      </article>
    </div>
  );
}
