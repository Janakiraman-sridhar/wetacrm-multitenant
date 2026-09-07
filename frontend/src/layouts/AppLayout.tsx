import clsx from "clsx";
import { ChevronLeft, ExternalLink, LogOut, Menu, Moon, ShieldCheck, Sun, X } from "lucide-react";
import { useMemo, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import logoMark from "@/assets/logo-mark.png";
import logoMarkDark from "@/assets/logo-mark-dark.png";
import { GlobalSearch } from "@/components/GlobalSearch";
import { NotificationsBell } from "@/components/NotificationsPanel";
import { Avatar } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { moduleIcon, useModules } from "@/lib/modules";
import { useVahanPortal } from "@/lib/settings";

/**
 * The sidebar is built from `/api/v1/modules`, not a list in this file.
 *
 * That is what lets one tenant see "Contacts" where another sees "Customers", and
 * lets a module be switched off per client — both without a code change. Module
 * keys stay stable; only the label and visibility vary.
 */
export function AppLayout() {
  const { user, logout, hasPerm, impersonating, impersonatedTenant, exitImpersonation } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const { data: modules } = useModules();
  const vahan = useVahanPortal();

  // Two filters, both needed: the tenant decides which modules exist at all, the
  // user's role decides which of those they may see.
  const nav = useMemo(
    () =>
      (modules ?? [])
        .filter((m) => !m.permission || hasPerm(m.permission))
        .map((m) => ({ to: m.route, label: m.label, icon: moduleIcon(m.icon) })),
    [modules, hasPerm]
  );

  const crumbs = useMemo(
    () => Object.fromEntries((modules ?? []).map((m) => [m.route, m.label])),
    [modules]
  );

  const sidebar = (
    <aside
      className={clsx(
        "flex h-full flex-col border-r border-slate-200 bg-white transition-all duration-200 dark:border-slate-800 dark:bg-slate-900",
        collapsed ? "w-16" : "w-60"
      )}
    >
      <div className={clsx("flex h-14 items-center gap-2.5 border-b border-slate-200 dark:border-slate-800", collapsed ? "justify-center px-2" : "px-4")}>
        {/* transparent mark; the dark theme swaps in the white-stroked variant */}
        <img src={logoMark} alt="WeTa CRM" className="h-8 w-auto shrink-0 object-contain dark:hidden" />
        <img src={logoMarkDark} alt="WeTa CRM" className="hidden h-8 w-auto shrink-0 object-contain dark:block" />
        {!collapsed && <span className="truncate text-lg font-bold">WeTa CRM</span>}
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {nav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary-50 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              )
            }
            title={collapsed ? label : undefined}
          >
            <Icon size={18} strokeWidth={1.8} className="shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        ))}
      </nav>
      <button
        className="hidden items-center justify-center gap-2 border-t border-slate-200 py-2.5 text-xs text-slate-400 hover:text-slate-600 dark:border-slate-800 lg:flex"
        onClick={() => setCollapsed(!collapsed)}
      >
        <ChevronLeft size={14} className={clsx("transition-transform", collapsed && "rotate-180")} />
        {!collapsed && "Collapse"}
      </button>
    </aside>
  );

  const crumb =
    crumbs[`/${location.pathname.split("/")[1]}`] ?? crumbs[location.pathname] ?? "Dashboard";

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Support session: make it impossible to forget whose data you are looking at. */}
      {impersonating && (
        <div className="flex shrink-0 items-center justify-center gap-3 bg-amber-500 px-4 py-1.5 text-sm font-medium text-amber-950">
          <ShieldCheck size={15} />
          <span>
            Viewing <strong>{impersonatedTenant}</strong> as a support session. Actions are recorded
            against your platform account.
          </span>
          <button
            onClick={exitImpersonation}
            className="ml-2 inline-flex items-center gap-1 rounded-md bg-amber-950/10 px-2 py-0.5 text-xs font-semibold transition-colors hover:bg-amber-950/20"
          >
            <X size={12} /> Exit
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1 overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden lg:block">{sidebar}</div>
      {/* Mobile sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" onClick={() => setMobileOpen(false)}>
          <div className="absolute inset-0 bg-slate-900/50" />
          <div className="absolute left-0 top-0 h-full" onClick={(e) => e.stopPropagation()}>
            {sidebar}
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4 dark:border-slate-800 dark:bg-slate-900">
          <button className="btn-ghost !p-2 lg:hidden" onClick={() => setMobileOpen(true)}>
            <Menu size={18} />
          </button>
          <nav className="hidden shrink-0 text-sm text-slate-400 sm:block">
            <span>WeTa CRM</span>
            <span className="mx-1.5">/</span>
            <span className="font-medium text-slate-700 dark:text-slate-200">{crumb}</span>
          </nav>
          <div className="flex flex-1 justify-center px-2">
            <GlobalSearch />
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {vahan?.enabled && vahan.url && (
              <a
                href={vahan.url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary !py-1.5 hidden sm:inline-flex"
                title="Open the Vahan vehicle registration portal in a new tab"
              >
                {vahan.label ?? "Vahan Portal"}
                <ExternalLink size={13} />
              </a>
            )}
            <button className="btn-ghost !p-2" onClick={toggleTheme} title="Toggle theme">
              {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            <NotificationsBell />
            <div className="mx-2 hidden items-center gap-2 sm:flex">
              <Avatar first={user?.first_name} last={user?.last_name} />
              <div className="leading-tight">
                <p className="text-sm font-medium">{user?.first_name}</p>
                <p className="text-[11px] text-slate-400">{user?.role?.name}</p>
              </div>
            </div>
            <button className="btn-ghost !p-2" onClick={logout} title="Sign out">
              <LogOut size={18} />
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
      </div>
    </div>
  );
}
