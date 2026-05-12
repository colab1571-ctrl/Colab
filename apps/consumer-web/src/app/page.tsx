import React from "react";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@colab/ui";

const features = [
  {
    title: "Discover",
    description: "Browse creators by vocation, location, and style.",
  },
  {
    title: "Connect",
    description: "Send a Vibe Check and start a collaboration.",
  },
  {
    title: "Create",
    description: "Build something great together with workspace tools.",
  },
];

export default function HomePage(): React.ReactElement {
  return (
    <main className="container mx-auto max-w-6xl px-4 py-12">
      <section
        className="flex flex-col items-center text-center mb-12"
        aria-labelledby="home-heading"
      >
        <h1
          id="home-heading"
          className="text-5xl font-bold text-[var(--color-brand-primary)] mb-4"
        >
          Colab
        </h1>
        <p className="text-lg text-[var(--color-muted-foreground)] max-w-xl">
          The creative collaboration platform for rising artists.
        </p>
        <div className="flex gap-4 mt-8" role="group" aria-label="Primary actions">
          <Button asChild>
            <a
              href="/login"
              className="focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              Get started
            </a>
          </Button>
          <Button variant="outline" asChild>
            <a
              href="/discover"
              className="focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              Discover creators
            </a>
          </Button>
        </div>
      </section>

      <section aria-labelledby="features-heading">
        <h2 id="features-heading" className="sr-only">Platform features</h2>
        <ul className="grid grid-cols-1 md:grid-cols-3 gap-6 list-none m-0 p-0">
          {features.map(({ title, description }) => (
            <li key={title}>
              <Card>
                <CardHeader>
                  <CardTitle>
                    <h3 className="text-base font-semibold">{title}</h3>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-[var(--color-muted-foreground)]">{description}</p>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
