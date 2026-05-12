import { Button, Card, CardContent, CardHeader, CardTitle } from "@colab/ui";

export default function HomePage(): React.ReactElement {
  return (
    <main className="container mx-auto max-w-6xl px-4 py-12">
      <div className="flex flex-col items-center text-center mb-12">
        <h1 className="text-5xl font-bold text-[var(--color-brand-primary)] mb-4">Colab</h1>
        <p className="text-lg text-[var(--color-muted-foreground)] max-w-xl">
          The creative collaboration platform for rising artists.
        </p>
        <div className="flex gap-4 mt-8">
          <Button asChild>
            <a href="/login">Get started</a>
          </Button>
          <Button variant="outline" asChild>
            <a href="/discover">Discover creators</a>
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {["Discover", "Connect", "Create"].map((title) => (
          <Card key={title}>
            <CardHeader>
              <CardTitle>{title}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-[var(--color-muted-foreground)]">
                {title === "Discover" && "Browse creators by vocation, location, and style."}
                {title === "Connect" && "Send a Vibe Check and start a collaboration."}
                {title === "Create" && "Build something great together with workspace tools."}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
