import { useSyncExternalStore } from 'react';

export type Theme = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'groundedpdf-theme';
const listeners = new Set<() => void>();

function readStoredTheme(): Theme {
  const saved = window.localStorage.getItem(STORAGE_KEY);
  return saved === 'light' || saved === 'dark' || saved === 'system' ? saved : 'system';
}

let currentTheme: Theme = readStoredTheme();

function resolveTheme(theme: Theme): 'light' | 'dark' {
  if (theme !== 'system') return theme;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyTheme(): void {
  const resolved = resolveTheme(currentTheme);
  document.documentElement.classList.toggle('dark', resolved === 'dark');
  document.documentElement.style.colorScheme = resolved;
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function setTheme(theme: Theme): void {
  currentTheme = theme;
  window.localStorage.setItem(STORAGE_KEY, theme);
  applyTheme();
  notify();
}

function subscribe(listener: () => void): () => void {
  if (listeners.size === 0) {
    // First subscriber: re-sync with storage (covers external resets, e.g. tests).
    const stored = readStoredTheme();
    if (stored !== currentTheme) {
      currentTheme = stored;
      queueMicrotask(notify);
    }
    applyTheme();
  }
  listeners.add(listener);

  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const onMediaChange = () => {
    if (currentTheme === 'system') applyTheme();
  };
  media.addEventListener('change', onMediaChange);

  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return;
    currentTheme = readStoredTheme();
    applyTheme();
    notify();
  };
  window.addEventListener('storage', onStorage);

  return () => {
    listeners.delete(listener);
    media.removeEventListener('change', onMediaChange);
    window.removeEventListener('storage', onStorage);
  };
}

function getSnapshot(): Theme {
  return currentTheme;
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, getSnapshot);
  return { theme, setTheme };
}
