import clsx from "clsx";
import { Building2, LayoutGrid, LogOut, Moon, Sun } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import logoMark from "@/assets/logo-mark.png";
import logoMarkDark from "@/assets/logo-mark-dark.png";
import { Avatar } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";

const NAV = [
  { to: "/platform", label: "Tenants", icon: Building2, end: true },
  { to: "/platform/templates", label: "Templates", icon: LayoutGrid, end: false },
];

/**
 * Shell for the Super Admin console.
 *
 * Deliberately a different chrome from the tenant CRM — darker, no module sidebar —
 * so it is never ambiguous whether you are administering the platform or working
 * inside one client's workspace.
 */
export function PlatformLayout() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="flex h-screen flex-col bg-slate-100 dark:bg-slate-950">
      <header className="flex h-14 shrink-0 items-center gap-4 border-b border-slate-800 bg-slate-900 px-4 text-slate-100">
        <div className="flex items-center gap-2.5">
          <img src={logoMark} alt="" className="h-7 w-auto object-contain dark:hidden" />
          <img src={logoMarkDark} alt="" className="hidden h-7 w-auto object-contain dark:block" />
          <span className="text-base font-bold">WeTa Platform</span>
          <span className="badge bg-primary-500/20 text-primary-300">Super Admin</span>
        </div>

        <nav className="ml-4 flex items-center gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                )
              }
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={toggleTheme}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200"
            title={theme === "dark" ? "Light mode" : "Dark mode"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <span className="flex items-center gap-2 text-sm">
            <Avatar first={user?.first_name ?? "P"} last={user?.last_name ?? ""} size={26} />
            <span className="hidden sm:inline">{user?.email}</span>
          </span>
          <button
            onClick={logout}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-800 hover:text-red-300"
            title="Sign out"
          >
            <LogOut size={17} />
          </button>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto p-5">
        <Outlet />
      </main>
    </div>
  );
}
