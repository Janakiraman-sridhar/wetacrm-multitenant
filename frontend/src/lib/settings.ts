import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

interface SettingRow {
  id: string;
  key: string;
  value: Record<string, any>;
}

/** All of this workspace's settings, keyed. */
export function useSettings() {
  return useQuery({
    queryKey: ["settings", "all"],
    queryFn: async () => {
      const rows = (await api.get<SettingRow[]>("/settings")).data;
      return Object.fromEntries(rows.map((row) => [row.key, row.value]));
    },
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export interface VahanPortal {
  enabled: boolean;
  url: string;
  label?: string;
}

/**
 * The Vahan portal shortcut, if this workspace has one.
 *
 * Seeded by the insurance template, so a general CRM tenant never sees the button.
 * The URL is a setting rather than a constant because the portal moves.
 */
export function useVahanPortal(): VahanPortal | null {
  const { data } = useSettings();
  const config = data?.vahan_portal as VahanPortal | undefined;
  return config?.enabled && config.url ? config : null;
}
