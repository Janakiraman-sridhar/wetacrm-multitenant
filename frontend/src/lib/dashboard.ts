import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface DashboardWidget {
  key: string;
  label: string;
  description: string;
  enabled: boolean;
  order: number;
  width: "full" | "half";
  requires: string | null;
  locked: boolean;
}

/**
 * Which cards this workspace's dashboard is built from, in order.
 *
 * The counterpart of `useModules` for the sidebar. The dashboard used to be a fixed
 * sequence in the page, so an insurance workspace opened on six deal figures reading
 * zero and a new vertical needed another `if` in that file.
 *
 * `all` includes the cards that are switched off, which only the editor wants.
 */
export function useDashboardLayout(all = false) {
  return useQuery({
    queryKey: ["dashboard-widgets", all],
    queryFn: async () =>
      (await api.get<DashboardWidget[]>("/dashboard-widgets", {
        params: all ? { all_widgets: true } : undefined,
      })).data,
    staleTime: 60_000,
  });
}

/** Every card that exists, whatever this workspace has switched on. */
export function useWidgetCatalog() {
  return useQuery({
    queryKey: ["dashboard-widget-catalog"],
    queryFn: async () =>
      (await api.get<DashboardWidget[]>("/dashboard-widgets/catalog")).data,
    staleTime: 10 * 60_000,
  });
}
