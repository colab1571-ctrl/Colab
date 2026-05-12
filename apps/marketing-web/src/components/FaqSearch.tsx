"use client";

import { useState, useId } from "react";
import type { FaqItem } from "../app/faq/page";

/**
 * Client-side text filter for FAQ items.
 * Minimal 'use client' island — renders a search input + filtered Q&A list.
 */
export function FaqSearch({ items }: { items: FaqItem[] }): React.ReactElement {
  const [query, setQuery] = useState("");
  const searchId = useId();

  const filtered = query.trim()
    ? items.filter(
        ({ question, answer }) =>
          question.toLowerCase().includes(query.toLowerCase()) ||
          answer.toLowerCase().includes(query.toLowerCase())
      )
    : items;

  return (
    <div>
      <div className="mb-8">
        <label
          htmlFor={searchId}
          className="block text-sm font-medium text-neutral-700 mb-2"
        >
          Search questions
        </label>
        <input
          id={searchId}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Type to filter…"
          className="w-full px-4 py-3 border border-neutral-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-primary)] focus:border-transparent"
          aria-controls="faq-list"
          aria-label="Filter FAQ questions"
        />
      </div>

      {filtered.length === 0 ? (
        <p
          className="text-neutral-400 text-sm text-center py-12"
          role="status"
          aria-live="polite"
        >
          No questions match &ldquo;{query}&rdquo;.
        </p>
      ) : (
        <dl
          id="faq-list"
          className="space-y-0 divide-y divide-neutral-100"
          aria-live="polite"
          aria-label={`${filtered.length} question${filtered.length === 1 ? "" : "s"}`}
        >
          {filtered.map(({ question, answer }) => (
            <div key={question} className="py-6">
              <dt className="text-lg font-semibold text-neutral-900 mb-2">
                {question}
              </dt>
              <dd className="text-neutral-600 leading-relaxed">{answer}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
