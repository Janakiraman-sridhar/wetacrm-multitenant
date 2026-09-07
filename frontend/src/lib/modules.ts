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
