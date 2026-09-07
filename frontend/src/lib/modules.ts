import { useQuery } from "@tanstack/react-query";
import * as Icons from "lucide-react";

import { api } from "@/lib/api";
import type { TenantModule } from "@/types";

/**
 * The current workspace's modules, as configured for this tenant.
 *
 * The sidebar is built from this rather than a hardcoded array, which is what lets
 * one client see "Contacts" and another "Customers" for the same module, and lets a
 * module be switched off per tenant without a code change.
 */
export function useModules(enabledOnly = true) {
  return useQuery({
    queryKey: ["modules", enabledOnly],
    queryFn: async () =>
      (await api.get<TenantModule[]>("/modules", { params: { enabled_only: enabledOnly } })).data,
    staleTime: 5 * 60_000,
  });
}

/** Resolve a lucide icon by the name the backend catalog stores. */
export function moduleIcon(name: string): Icons.LucideIcon {
  const icon = (Icons as unknown as Record<string, Icons.LucideIcon>)[name];
  return icon ?? Icons.Circle;
}

/**
 * Whether this workspace has a module switched on.
 *
 * The API refuses a disabled module outright, so an action button gated only on a
 * permission can offer something that will come back 404 — "Convert to invoice" on
 * a workspace with no Invoices. Gate on both.
 */
export function useHasModule() {
  const { data } = useModules();
  return (key: string) => (data ?? []).some((m) => m.module_key === key);
}
