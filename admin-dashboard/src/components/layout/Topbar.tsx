import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Sun, UserRound } from 'lucide-react';
import { Badge, Button } from '@/components/ui/primitives';
import { useAuth } from '@/auth/AuthContext';
import { useTheme } from '@/lib/theme';
import { useToast } from '@/components/ui/Toast';
import { NAV_ITEMS } from './Sidebar';
import { cn } from '@/lib/utils';

function usePageTitle() {
  const { pathname } = useLocation();
  const match = [...NAV_ITEMS]
    .sort((a, b) => b.to.length - a.to.length)
    .find((item) => (item.to === '/' ? pathname === '/' : pathname.startsWith(item.to)));
  return match?.label ?? 'Console';
}

export function Topbar({
  collapsed,
  onToggleCollapse,
  onOpenMobileNav,
}: {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onOpenMobileNav: () => void;
}) {
  const title = usePageTitle();
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const toast = useToast();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false);
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  const handleLogout = async () => {
    setSigningOut(true);
    try {
      await logout();
      toast.success('Signed out', 'Your session was closed.');
      navigate('/login', { replace: true });
    } catch {
      toast.error('Sign out failed', 'Please try again.');
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-surface/85 px-3 backdrop-blur-md sm:px-4">
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label="Open navigation"
        className="rounded-lg p-2 text-muted transition-colors hover:bg-elevated hover:text-ink md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      <button
        type="button"
        onClick={onToggleCollapse}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        className="hidden rounded-lg p-2 text-muted transition-colors hover:bg-elevated hover:text-ink md:inline-flex"
      >
        {collapsed ? <PanelLeftOpen className="h-[18px] w-[18px]" /> : <PanelLeftClose className="h-[18px] w-[18px]" />}
      </button>

      <div className="ml-1 min-w-0 flex-1">
        <h1 className="truncate text-sm font-semibold text-ink sm:text-base">{title}</h1>
      </div>

      <button
        type="button"
        onClick={toggle}
        aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
        className="rounded-lg p-2 text-muted transition-colors hover:bg-elevated hover:text-ink"
      >
        {theme === 'dark' ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
      </button>

      <div className="relative" ref={menuRef}>
        <button
          type="button"
          onClick={() => setMenuOpen((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 transition-colors hover:bg-elevated"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand/15 text-xs font-semibold text-brand-ink">
            {user?.initials ?? '??'}
          </span>
          <span className="hidden text-left sm:block">
            <span className="block max-w-[120px] truncate text-xs font-medium leading-tight text-ink">
              {user?.name}
            </span>
            <span className="block text-[11px] capitalize leading-tight text-faint">{user?.role}</span>
          </span>
        </button>

        {menuOpen && (
          <div
            role="menu"
            className="absolute right-0 top-11 w-56 animate-slide-up overflow-hidden rounded-xl border border-line bg-surface shadow-pop"
          >
            <div className="border-b border-line px-3.5 py-3">
              <p className="truncate text-sm font-semibold text-ink">{user?.name}</p>
              <p className="truncate text-xs text-muted">{user?.email}</p>
              <Badge tone="brand" className="mt-2 capitalize">
                {user?.role} account
              </Badge>
            </div>
            <div className="p-1.5">
              <button
                type="button"
                role="menuitem"
                disabled
                className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-muted opacity-60"
              >
                <UserRound className="h-4 w-4" />
                Profile
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={handleLogout}
                disabled={signingOut}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-danger transition-colors hover:bg-danger/10',
                  signingOut && 'opacity-60',
                )}
              >
                <LogOut className="h-4 w-4" />
                {signingOut ? 'Signing out…' : 'Sign out'}
              </button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h2 className="text-lg font-semibold tracking-tight text-ink sm:text-xl">{title}</h2>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export { Button };
