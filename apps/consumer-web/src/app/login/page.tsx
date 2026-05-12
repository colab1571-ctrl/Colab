import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@colab/ui";

export default function LoginPage(): React.ReactElement {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Welcome back</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label htmlFor="email" className="text-sm font-medium text-[var(--color-foreground)]">Email</label>
            <Input id="email" type="email" placeholder="you@example.com" className="mt-1" />
          </div>
          <div>
            <label htmlFor="password" className="text-sm font-medium text-[var(--color-foreground)]">Password</label>
            <Input id="password" type="password" placeholder="••••••••" className="mt-1" />
          </div>
          <Button className="w-full">Sign In</Button>
          <p className="text-center text-sm text-[var(--color-muted-foreground)]">
            Full auth flow implemented in P2 (auth-svc).
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
