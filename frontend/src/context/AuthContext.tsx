import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, tokenStore } from "@/lib/api";
import { connectSocket, disconnectSocket } from "@/lib/socket";
import type { User } from "@/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  hasPerm: (perm: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

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
    tokenStore.clear();
    disconnectSocket();
    setUser(null);
    window.location.href = "/login";
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
    () => ({ user, loading, login, logout, refreshUser, hasPerm }),
    [user, loading, login, logout, refreshUser, hasPerm]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
