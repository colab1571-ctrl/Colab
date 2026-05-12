/**
 * Required by @next/mdx — this file defines the components available
 * to all MDX files in the project.
 * See: https://nextjs.org/docs/app/building-your-application/configuring/mdx#add-the-mdx-components-file
 */

import type { MDXComponents } from "mdx/types";

export function useMDXComponents(components: MDXComponents): MDXComponents {
  return {
    // Re-use default components (h1..h6, p, a, etc.) with any customisations
    h1: ({ children, ...props }) => (
      <h1 className="text-3xl font-bold text-neutral-900 mb-6" {...props}>
        {children}
      </h1>
    ),
    h2: ({ children, ...props }) => (
      <h2
        className="text-2xl font-bold text-neutral-900 mt-10 mb-4 scroll-mt-24"
        {...props}
      >
        {children}
      </h2>
    ),
    h3: ({ children, ...props }) => (
      <h3
        className="text-xl font-semibold text-neutral-900 mt-8 mb-3 scroll-mt-24"
        {...props}
      >
        {children}
      </h3>
    ),
    p: ({ children, ...props }) => (
      <p className="text-neutral-600 leading-relaxed mb-4" {...props}>
        {children}
      </p>
    ),
    a: ({ children, href, ...props }) => (
      <a
        href={href}
        className="text-[var(--color-brand-primary)] underline underline-offset-2 hover:opacity-80 transition-opacity"
        {...(href?.startsWith("http")
          ? { target: "_blank", rel: "noopener noreferrer" }
          : {})}
        {...props}
      >
        {children}
      </a>
    ),
    ul: ({ children, ...props }) => (
      <ul
        className="list-disc list-inside space-y-2 mb-4 text-neutral-600"
        {...props}
      >
        {children}
      </ul>
    ),
    ol: ({ children, ...props }) => (
      <ol
        className="list-decimal list-inside space-y-2 mb-4 text-neutral-600"
        {...props}
      >
        {children}
      </ol>
    ),
    li: ({ children, ...props }) => (
      <li className="leading-relaxed" {...props}>
        {children}
      </li>
    ),
    blockquote: ({ children, ...props }) => (
      <blockquote
        className="border-l-4 border-[var(--color-brand-primary)] pl-4 italic text-neutral-500 my-4"
        {...props}
      >
        {children}
      </blockquote>
    ),
    table: ({ children, ...props }) => (
      <div className="overflow-x-auto my-6">
        <table className="w-full text-sm border-collapse" {...props}>
          {children}
        </table>
      </div>
    ),
    th: ({ children, ...props }) => (
      <th
        className="bg-neutral-50 text-left px-4 py-2 font-semibold text-neutral-700 border border-neutral-200"
        {...props}
      >
        {children}
      </th>
    ),
    td: ({ children, ...props }) => (
      <td
        className="px-4 py-2 text-neutral-600 border border-neutral-200"
        {...props}
      >
        {children}
      </td>
    ),
    hr: (props) => (
      <hr className="border-neutral-200 my-8" {...props} />
    ),
    code: ({ children, ...props }) => (
      <code
        className="bg-neutral-100 text-neutral-800 px-1.5 py-0.5 rounded text-sm font-mono"
        {...props}
      >
        {children}
      </code>
    ),
    pre: ({ children, ...props }) => (
      <pre
        className="bg-neutral-900 text-neutral-100 rounded-xl p-6 overflow-x-auto my-6 text-sm"
        {...props}
      >
        {children}
      </pre>
    ),
    ...components,
  };
}
