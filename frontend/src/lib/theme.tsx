import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

/**
 * Theme system — light / dark / system.
 *
 * The resolved theme is applied as a `dark` class on <html>, which the
 * Tailwind v4 `@custom-variant dark` in index.css keys off. The choice is
 * persisted in localStorage under `warden-theme` and defaults to the OS
 * preference. When set to `system`, it follows OS changes live.
 */

export type Theme = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'warden-theme';

function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getStoredTheme(): Theme {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === 'light' || v === 'dark' || v === 'system') return v;
  } catch {
    // Storage unavailable (private mode, etc.) — fall through to system.
  }
  return 'system';
}

function resolveTheme(theme: Theme): ResolvedTheme {
  return theme === 'system' ? getSystemTheme() : theme;
}

function applyTheme(resolved: ResolvedTheme) {
  document.documentElement.classList.toggle('dark', resolved === 'dark');
}

type ThemeContextValue = {
  /** The user's stored preference ('system' follows the OS). */
  theme: Theme;
  /** The theme actually in effect after resolving 'system'. */
  resolved: ResolvedTheme;
  setTheme: (t: Theme) => void;
  /** Flip between light and dark (ignores 'system' — stores the explicit choice). */
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => getStoredTheme());
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolveTheme(getStoredTheme()));

  // Apply + persist whenever the preference changes.
  useEffect(() => {
    const r = resolveTheme(theme);
    setResolved(r);
    applyTheme(r);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Ignore storage failures.
    }
  }, [theme]);

  // Follow the OS while the preference is 'system'.
  useEffect(() => {
    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      const r = getSystemTheme();
      setResolved(r);
      applyTheme(r);
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [theme]);

  const setTheme = useCallback((t: Theme) => setThemeState(t), []);
  const toggleTheme = useCallback(() => {
    setThemeState((prev) => (resolveTheme(prev) === 'dark' ? 'light' : 'dark'));
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, resolved, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within <ThemeProvider>');
  return ctx;
}

/**
 * Apply the stored/system theme before React mounts. Call once from
 * main.tsx (and mirror it in index.html) so a dark-mode user never sees
 * a white flash on first paint.
 */
export function initTheme() {
  applyTheme(resolveTheme(getStoredTheme()));
}
