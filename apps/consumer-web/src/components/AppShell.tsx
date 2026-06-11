"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@colab/ui";

const NAV_ITEMS = [
  { href: "/discover", label: "Discover" },
  { href: "/inbox", label: "Inbox" },
  { href: "/chats", label: "Chats" },
] as const;

/**
 * Top-level app shell with nav + auth-aware account menu.
 *
 * Wraps every consumer-web page. Anonymous visitors see Sign in + Get started
 * CTAs; signed-in users see the main nav + an account dropdown with profile,
 * settings, and sign out.
 */
export function AppShell({ children }: { children: React.ReactNode }): React.ReactElement {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const onSignOut = async () => {
    await signOut();
    setMenuOpen(false);
    router.push("/");
  };

  const isAuthRoute = pathname?.startsWith("/login") || pathname?.startsWith("/signup") || pathname?.startsWith("/forgot-password") || pathname?.startsWith("/onboarding");

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-background)]/95 backdrop-blur supports-[backdrop-filter]:bg-[var(--color-background)]/75">
        <div className="container mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Link
            href={user ? "/discover" : "/"}
            className="text-lg font-bold text-[var(--color-brand-primary)] focus-visible:outline-2 focus-visible:outline-[var(--color-brand-primary)]"
          >
            Colab
          </Link>

          {user && !isAuthRoute && (
            <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
              {NAV_ITEMS.map((item) => {
                const active = pathname?.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-[var(--color-brand-primary)] ${
                      active
                        ? "bg-[var(--color-muted)] text-[var(--color-foreground)]"
                        : "text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-muted)]"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          )}

          <div className="flex items-center gap-2">
            {loading ? (
              <div
                className="h-8 w-20 animate-pulse rounded-md bg-[var(--color-muted)]"
                aria-hidden="true"
              />
            ) : user ? (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setMenuOpen((o) => !o)}
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  className="flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-background)] py-1 pl-1 pr-3 text-sm hover:bg-[var(--color-muted)] focus-visible:outline-2 focus-visible:outline-[var(--color-brand-primary)]"
                >
                  <span
                    className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--color-brand-primary)] text-xs font-semibold text-[var(--color-primary-foreground)]"
                    aria-hidden="true"
                  >
                    {user.email[0]?.toUpperCase() ?? "?"}
                  </span>
                  <span className="hidden sm:inline truncate max-w-[12ch]">{user.email}</span>
                </button>
                {menuOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 mt-2 w-56 rounded-md border border-[var(--color-border)] bg-[var(--color-card)] py-1 shadow-lg"
                  >
                    <Link
                      href="/profile/me"
                      role="menuitem"
                      className="block px-3 py-2 text-sm text-[var(--color-foreground)] hover:bg-[var(--color-muted)] focus-visible:bg-[var(--color-muted)] focus-visible:outline-none"
                      onClick={() => setMenuOpen(false)}
                    >
                      Your profile
                    </Link>
                    <Link
                      href="/settings"
                      role="menuitem"
                      className="block px-3 py-2 text-sm text-[var(--color-foreground)] hover:bg-[var(--color-muted)] focus-visible:bg-[var(--color-muted)] focus-visible:outline-none"
                      onClick={() => setMenuOpen(false)}
                    >
                      Settings
                    </Link>
                    <div className="my-1 border-t border-[var(--color-border)]" aria-hidden="true" />
                    <button
                      type="button"
                      role="menuitem"
                      onClick={onSignOut}
                      className="block w-full px-3 py-2 text-left text-sm text-[var(--color-destructive)] hover:bg-[var(--color-muted)] focus-visible:bg-[var(--color-muted)] focus-visible:outline-none"
                    >
                      Sign out
                    </button>
                  </div>
                )}
              </div>
            ) : !isAuthRoute ? (
              <>
                <Link
                  href="/login"
                  className="rounded-md px-3 py-1.5 text-sm font-medium text-[var(--color-foreground)] hover:bg-[var(--color-muted)] focus-visible:outline-2 focus-visible:outline-[var(--color-brand-primary)]"
                >
                  Sign in
                </Link>
                <Link
                  href="/signup"
                  className="rounded-md bg-[var(--color-brand-primary)] px-3 py-1.5 text-sm font-medium text-[var(--color-primary-foreground)] hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-brand-primary)]"
                >
                  Get started
                </Link>
              </>
            ) : null}
          </div>
        </div>
      </header>

      <div>{children}</div>
    </>
  );
}
