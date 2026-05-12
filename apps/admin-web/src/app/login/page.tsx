import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@colab/ui";

export default function AdminLoginPage(): React.ReactElement {
  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-100 px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Admin Console</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-[var(--color-muted-foreground)]">
            IP-allowlisted + admin role required.
          </p>
          <Input type="email" placeholder="admin@colab.app" />
          <Input type="password" placeholder="••••••••" />
          <Button className="w-full">Sign In</Button>
        </CardContent>
      </Card>
    </main>
  );
}
