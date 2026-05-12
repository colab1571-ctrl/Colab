/**
 * Thin wrapper for injecting JSON-LD structured data into a page.
 * Usage: <JsonLd data={faqPageSchema} id="faq-schema" />
 */
export function JsonLd({
  data,
  id,
}: {
  data: Record<string, unknown>;
  id: string;
}): React.ReactElement {
  return (
    <script
      id={id}
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}
