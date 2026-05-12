"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";

interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

const STORAGE_KEY = "colab-theme";
const COOKIE_KEY = "colab-theme";

interface ThemeProviderProps {
  children: React.ReactNode;
  defaultTheme?: Theme;
  /** If true, persist theme in cookie (for SSR match). */
  cookiePersist?: boolean;
}

export function ThemeProvider({
  children,
  defaultTheme = "system",
  cookiePersist = true,
}: ThemeProviderProps): React.ReactElement {
  const [theme, setThemeState] = useState<Theme>(defaultTheme);
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("light");

  const applyTheme = useCallback(
    (t: Theme) => {
      const resolved: "light" | "dark" =
        t === "system"
          ? window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light"
          : t;
      document.documentElement.setAttribute("data-theme", resolved);
      setResolvedTheme(resolved);
      if (cookiePersist) {
        document.cookie = `${COOKIE_KEY}=${t}; path=/; max-age=31536000; SameSite=Lax`;
      }
      try {
        localStorage.setItem(STORAGE_KEY, t);
      } catch {
        // ignore in private browsing
      }
    },
    [cookiePersist]
  );

  useEffect(() => {
    // Read persisted preference
    let persisted: Theme = defaultTheme;
    try {
      persisted = (localStorage.getItem(STORAGE_KEY) as Theme) || defaultTheme;
    } catch {
      /* ignore */
    }
    setThemeState(persisted);
    applyTheme(persisted);

    // Listen to system preference changes
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      if (theme === "system") applyTheme("system");
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const setTheme = useCallback(
    (t: Theme) => {
      setThemeState(t);
      applyTheme(t);
    },
    [applyTheme]
  );

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
