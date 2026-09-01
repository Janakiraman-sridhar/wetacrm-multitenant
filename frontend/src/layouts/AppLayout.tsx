import clsx from "clsx";
import {
  BarChart3, Box, Briefcase, Building2, Calendar, CheckSquare, ChevronLeft, Contact2,
  FileText, Kanban, LayoutDashboard, LifeBuoy, LogOut, Menu, Moon, Receipt, Settings,
  Sun, Target, TrendingUp,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import logoMark from "@/assets/logo-mark.png";
import { GlobalSearch } from "@/components/GlobalSearch";
import { NotificationsBell } from "@/components/NotificationsPanel";
import { Avatar } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, perm: null },
  { to: "/companies", label: "Companies", icon: Building2, perm: "companies:read" },
  { to: "/contacts", label: "Contacts", icon: Contact2, perm: "contacts:read" },
  { to: "/leads", label: "Leads", icon: Target, perm: "leads:read" },
  { to: "/deals", label: "Deals", icon: TrendingUp, perm: "deals:read" },
  { to: "/pipeline", label: "Pipeline", icon: Kanban, perm: "deals:read" },
  { to: "/calendar", label: "Calendar", icon: Calendar, perm: "calendar:read" },
  { to: "/tasks", label: "Tasks", icon: CheckSquare, perm: "tasks:read" },
  { to: "/projects", label: "Projects", icon: Briefcase, perm: "projects:read" },
  { to: "/products", label: "Products", icon: Box, perm: "products:read" },
  { to: "/quotations", label: "Quotations", icon: FileText, perm: "quotations:read" },
  { to: "/invoices", label: "Invoices", icon: Receipt, perm: "invoices:read" },
  { to: "/support", label: "Support", icon: LifeBuoy, perm: "support:read" },
  { to: "/reports", label: "Reports", icon: BarChart3, perm: "reports:read" },
  { to: "/settings", label: "Settings", icon: Settings, perm: "settings:read" },
];

const CRUMBS: Record<string, string> = Object.fromEntries(NAV.map((n) => [n.to, n.label]));

export function AppLayout() {
  const { user, logout, hasPerm } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  const nav = NAV.filter((n) => !n.perm || hasPerm(n.perm));

  const sidebar = (
    <aside
      className={clsx(
        "flex h-full flex-col border-r border-slate-200 bg-white transition-all duration-200 dark:border-slate-800 dark:bg-slate-900",
        collapsed ? "w-16" : "w-60"
      )}
    >
      <div className={clsx("flex h-14 items-center gap-2.5 border-b border-slate-200 dark:border-slate-800", collapsed ? "justify-center px-2" : "px-4")}>
        <img src={logoMark} alt="WeTa CRM" className="h-8 w-auto shrink-0 object-contain" />
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
            <Icon size={18} className="shrink-0" />
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

  const crumb = CRUMBS[`/${location.pathname.split("/")[1]}`] ?? CRUMBS[location.pathname] ?? "Dashboard";

  return (
    <div className="flex h-screen overflow-hidden">
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
  );
}
