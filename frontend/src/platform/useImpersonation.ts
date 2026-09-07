import { useMutation } from "@tanstack/react-query";

import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { startImpersonation } from "@/lib/impersonation";

/**
 * "Open workspace" — the one way a platform admin reaches a tenant's data.
 *
 * Shared by the tenant list and the tenant page so the two cannot drift, and so the
 * failure handling lives in one place. That matters: the previous version stored the
 * session and navigated inside a mutation's `onSuccess`, where a throw is *not*
 * routed to `onError` — a blocked `localStorage` or an unexpected response produced a
 * button that did nothing at all, with no message. Here every step that can fail is
 * inside the mutation function, so anything that goes wrong surfaces as a toast.
 */
export function useOpenWorkspace() {
  const { toast } = useToast();

  return useMutation({
    mutationFn: async (tenantId: string) => {
      const { data } = await api.post(`/platform/tenants/${tenantId}/impersonate`, {});
      if (!data?.access_token || !data?.tenant?.id) {
        throw new Error("The server did not return a usable session for this workspace.");
      }
      startImpersonation(data.access_token, data.tenant.id, data.tenant.name, data.acting_as_email);
      return data;
    },
    onSuccess: (data) => {
      toast(`Opening ${data.tenant.name} as ${data.acting_as_email}`);
      // A full load rather than a router push: the whole app re-reads its identity,
      // modules and permissions from the new session.
      window.location.href = "/";
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });
}
