import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, tokenStore } from "@/lib/api";
import { isImpersonating, readImpersonation, stopImpersonation } from "@/lib/impersonation";
import { connectSocket, disconnectSocket } from "@/lib/socket";
import type { User } from "@/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  hasPerm: (perm: string) => boolean;
  /** True while a platform admin is acting inside a tenant workspace. */
  impersonating: boolean;
  /** Name of the workspace being impersonated, for the banner. */
  impersonatedTenant: string | null;
  exitImpersonation: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [impersonating, setImpersonating] = useState(() => isImpersonating());
  const impersonatedTenant = readImpersonation()?.tenantName ?? null;

  const refreshUser = useCallback(async () => {
    const { data } = await api.get<User>("/auth/me");
    setUser(data);
  }, []);

  useEffect(() => {
    (async () => {
      if (tokenStore.access) {
        try {
          await refreshUser();
          connectSocket();
        } catch {
          tokenStore.clear();
        }
      }
      setLoading(false);
    })();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post("/auth/login", { email, password });
    tokenStore.set(data.access_token, data.refresh_token);
    setUser(data.user);
    if (!data.user?.is_platform_admin) connectSocket();
  }, []);

  const logout = useCallback(() => {
    stopImpersonation();
    tokenStore.clear();
    disconnectSocket();
    setUser(null);
    window.location.href = "/login";
  }, []);

  /** Hand the platform admin their own session back and return them to the console. */
  const exitImpersonation = useCallback(() => {
    stopImpersonation();
    setImpersonating(false);
    disconnectSocket();
    window.location.href = "/platform";
  }, []);

  const hasPerm = useCallback(
    (perm: string) => {
      const perms = user?.role?.permissions ?? [];
      if (perms.includes("*") || perms.includes(perm)) return true;
      return perms.includes(`${perm.split(":")[0]}:*`);
    },
    [user]
  );

  const value = useMemo(
    () => ({
      user, loading, login, logout, refreshUser, hasPerm,
      impersonating, impersonatedTenant, exitImpersonation,
    }),
    [user, loading, login, logout, refreshUser, hasPerm, impersonating, impersonatedTenant, exitImpersonation]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
