import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  PhoneCall,
  Settings,
  Users,
  X,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  badge?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/leads', label: 'Leads', icon: Users },
  { to: '/calls', label: 'Call Log', icon: PhoneCall },
  { to: '/automations', label: 'Automations', icon: Zap },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export function Sidebar({
  collapsed,
  mobileOpen,
  onCloseMobile,
}: {
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  return (
    <>
      {/* Mobile scrim */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 animate-fade-in bg-black/60 md:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex flex-col border-r border-line bg-surface transition-[width,transform] duration-200 ease-out',
          'w-[248px]',
          // Desktop: collapsible rail vs full width
          collapsed ? 'md:w-[68px]' : 'md:w-[248px]',
          // Mobile: off-canvas drawer
          mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
        )}
        aria-label="Primary navigation"
      >
        {/* Brand */}
        <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand text-sm font-bold text-white">
            LG
          </div>
          <div className={cn('min-w-0 flex-1', collapsed && 'md:hidden')}>
            <p className="truncate text-sm font-semibold leading-tight text-ink">LeadsGen AI</p>
            <p className="truncate text-[11px] leading-tight text-faint">Admin Console</p>
          </div>
          <button
            type="button"
            onClick={onCloseMobile}
            aria-label="Close navigation"
            className="rounded-lg p-1.5 text-faint transition-colors hover:bg-elevated hover:text-ink md:hidden"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          <ul className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  onClick={onCloseMobile}
                  title={item.label}
                  className={({ isActive }) =>
                    cn(
                      'group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-brand/12 text-brand-ink'
                        : 'text-muted hover:bg-elevated hover:text-ink',
                      collapsed && 'md:justify-center md:px-0',
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-brand" />
                      )}
                      <item.icon className="h-[18px] w-[18px] shrink-0" />
                      <span className={cn('truncate', collapsed && 'md:hidden')}>{item.label}</span>
                      {item.badge && !collapsed && (
                        <span className="ml-auto rounded-full bg-brand/20 px-1.5 py-0.5 text-[10px] font-semibold text-brand-ink">
                          {item.badge}
                        </span>
                      )}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {/* Footer hint */}
        <div className={cn('shrink-0 border-t border-line p-3', collapsed && 'md:hidden')}>
          <div className="rounded-lg bg-elevated px-3 py-2.5">
            <p className="text-[11px] font-semibold text-ink">Free-tier AI stack</p>
            <p className="mt-0.5 text-[11px] leading-snug text-faint">
              Mistral · Groq · Cerebras · EdgeTTS — no paid inference.
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
