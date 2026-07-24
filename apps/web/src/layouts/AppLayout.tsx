import { FileText, Menu, MessageSquareText, Search, Settings, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router';
import { Logo } from '../components/Logo';
import { useModalBehavior } from '../hooks/useModalBehavior';
import { useTheme } from '../hooks/useTheme';

const links = [
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/chat', label: 'Chat', icon: MessageSquareText },
  { to: '/search', label: 'Search', icon: Search },
  { to: '/settings', label: 'Settings', icon: Settings },
];

/** ⌘K / Ctrl+K anywhere in the app opens quote search (the page focuses its input). */
function useSearchShortcut() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (pathname !== '/search') void navigate('/search');
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [navigate, pathname]);
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-white dark:bg-ink-900">
      <div className="flex h-16 items-center border-b px-5">
        <Logo />
      </div>
      <nav className="flex-1 space-y-1 p-3" aria-label="Primary navigation">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-accent-50 text-accent-800 dark:bg-accent-950 dark:text-accent-200'
                  : 'text-ink-600 hover:bg-ink-50 hover:text-ink-950 dark:text-ink-300 dark:hover:bg-ink-800 dark:hover:text-white'
              }`
            }
          >
            <Icon className="size-5" aria-hidden="true" />
            {label}
          </NavLink>
        ))}
      </nav>
      <p className="border-t px-5 py-4 text-xs text-ink-500 dark:text-ink-400">
        Local-first · v{__APP_VERSION__}
      </p>
    </div>
  );
}

export function AppLayout() {
  // Keeps the html `dark` class managed on every page, not just Settings.
  useTheme();
  useSearchShortcut();
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeMobile = useCallback(() => setMobileOpen(false), []);
  useModalBehavior(mobileOpen, closeMobile);
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[240px_minmax(0,1fr)]">
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-accent-700 px-4 py-2 text-sm font-semibold text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to content
      </a>
      <aside className="hidden border-r lg:block">
        <div className="fixed inset-y-0 w-[240px]">
          <Sidebar />
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-white/95 px-4 backdrop-blur dark:bg-ink-900/95 lg:hidden">
          <Logo />
          <button
            className="button-ghost px-2"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="size-5" />
          </button>
        </header>
        <main id="main" tabIndex={-1} className="min-h-dvh focus-visible:ring-0 lg:min-h-0">
          <Outlet />
        </main>
      </div>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/40" aria-hidden="true" onClick={closeMobile} />
          <aside
            className="relative h-full w-72 border-r shadow-2xl motion-safe:animate-message-in"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
          >
            <button
              className="button-ghost absolute right-2 top-3 z-10 px-2"
              onClick={closeMobile}
              aria-label="Close navigation"
            >
              <X className="size-5" />
            </button>
            <Sidebar onNavigate={closeMobile} />
          </aside>
        </div>
      )}
    </div>
  );
}
