import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import { Modal } from "@/components/Modal";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";

interface DeletedTenant {
  id: string;
  name: string;
  slug: string;
  deleted_at: string;
  days_until_purge: number;
  retention_days: number;
  protected: boolean;
}

/**
 * Workspaces inside the retention window.
 *
 * Deleting is only undoable while the row is still here, so the console needs to
 * show what is in the window rather than letting an admin discover afterwards that
 * it has gone. The purge-now button exists for one reason: honouring a "delete my
 * data now" request without waiting out thirty days.
 */
export function DeletedTenants() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [purging, setPurging] = useState<DeletedTenant | null>(null);
  const [confirmSlug, setConfirmSlug] = useState("");

  const deleted = useQuery({
    queryKey: ["platform", "deleted-tenants"],
    queryFn: async () => (await api.get<DeletedTenant[]>("/platform/deleted-tenants")).data,
  });

  const purge = useMutation({
    mutationFn: async (tenant: DeletedTenant) =>
      (await api.post(`/platform/tenants/${tenant.id}/purge`, null, {
        params: { confirm: confirmSlug.trim() },
      })).data,
    onSuccess: (result: { detail: string }) => {
      toast(result.detail);
      setPurging(null);
      setConfirmSlug("");
      queryClient.invalidateQueries({ queryKey: ["platform"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const rows = deleted.data ?? [];
  if (rows.length === 0) return null;

  return (
    <section className="card p-5">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <h2 className="font-semibold">Deleted workspaces</h2>
        <span className="text-sm text-slate-400">
          {rows.length} awaiting purge
        </span>
      </div>
      <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
        Kept for {rows[0].retention_days} days so a mistaken delete can be undone, then
        removed permanently — every row, every uploaded file, every search entry. Ask
        support to restore one while it is still here.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
              <th className="px-2 py-2 font-semibold">Workspace</th>
              <th className="px-2 py-2 font-semibold">Deleted</th>
              <th className="px-2 py-2 font-semibold">Purged in</th>
              <th className="px-2 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800/60">
                <td className="px-2 py-2">
                  <span className="block font-medium">{t.name}</span>
                  <span className="block text-xs text-slate-400">/{t.slug}</span>
                </td>
                <td className="px-2 py-2 text-slate-500 dark:text-slate-400">
                  {formatDate(t.deleted_at)}
                </td>
                <td className="px-2 py-2">
                  <span
                    className={clsx(
                      "badge",
                      t.days_until_purge <= 3
                        ? "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
                        : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                    )}
                  >
                    {t.days_until_purge === 0
                      ? "at the next purge"
                      : `${t.days_until_purge} day${t.days_until_purge === 1 ? "" : "s"}`}
                  </span>
                </td>
                <td className="px-2 py-2 text-right">
                  {t.protected ? (
                    <span className="text-xs text-slate-400">protected</span>
                  ) : (
                    <button
                      className="btn-ghost !px-2 !py-1 text-xs text-red-500"
                      title="Remove permanently, now, without waiting out the window"
                      onClick={() => {
                        setConfirmSlug("");
                        setPurging(t);
                      }}
                    >
                      <Trash2 size={13} /> Purge now
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal open={!!purging} onClose={() => setPurging(null)} title={`Purge ${purging?.name ?? ""}?`}>
        <div className="space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Every record, uploaded file and search entry belonging to this workspace is
            removed immediately and permanently. It will not be in any backup taken from
            now on. <strong>There is no undo.</strong>
          </p>
          <div>
            <label className="label">Type the slug to confirm</label>
            <input
              className="input font-mono"
              placeholder={purging?.slug}
              value={confirmSlug}
              onChange={(e) => setConfirmSlug(e.target.value)}
              autoFocus
            />
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setPurging(null)}>
              Cancel
            </button>
            <button
              className="btn-danger"
              disabled={confirmSlug.trim() !== purging?.slug || purge.isPending}
              onClick={() => purging && purge.mutate(purging)}
            >
              {purge.isPending ? "Purging…" : "Purge permanently"}
            </button>
          </div>
        </div>
      </Modal>
    </section>
  );
}
