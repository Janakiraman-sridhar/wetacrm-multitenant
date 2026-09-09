import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { DashboardBoard, WidgetSetting } from "@/components/DashboardBoard";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { useDashboardLayout, useWidgetCatalog } from "@/lib/dashboard";
import { useModules } from "@/lib/modules";

/**
 * This workspace's own dashboard.
 *
 * A template decides what a workspace *opens* with; two agencies on the same
 * template will still want different things, so the layout is editable here in the
 * same way modules are. Editing it never touches the template — provisioning copies,
 * it does not reference.
 */
export function DashboardTab({ canWrite }: { canWrite: boolean }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data: layout } = useDashboardLayout(true);
  const { data: catalog } = useWidgetCatalog();
  const { data: modules } = useModules();
  const [draft, setDraft] = useState<WidgetSetting[]>([]);
  const saved = useRef("");

  useEffect(() => {
    if (!layout) return;
    const rows = layout.map((w) => ({ key: w.key, enabled: w.enabled, order: w.order }));
    setDraft(rows);
    saved.current = JSON.stringify(rows);
  }, [layout]);

  const dirty = saved.current !== "" && JSON.stringify(draft) !== saved.current;

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.put(
          "/dashboard-widgets",
          draft.map((w, index) => ({ key: w.key, enabled: w.enabled, order: index + 1 }))
        )
      ).data,
    onSuccess: () => {
      toast("Dashboard updated");
      saved.current = JSON.stringify(draft);
      queryClient.invalidateQueries({ queryKey: ["dashboard-widgets"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  if (!layout || !catalog) return <p className="text-slate-400">Loading…</p>;

  const enabledModules = new Set((modules ?? []).map((m) => m.module_key));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm text-slate-500 dark:text-slate-400">
          What everyone in this workspace sees when they sign in, and in what order.
          A card whose module is switched off is never shown, whatever is set here.
        </p>
        {canWrite && (
          <button
            className="btn-primary ml-auto shrink-0"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate()}
          >
            <Save size={15} /> {save.isPending ? "Saving…" : dirty ? "Save changes" : "Saved"}
          </button>
        )}
      </div>

      <DashboardBoard
        catalog={catalog}
        value={draft}
        onChange={setDraft}
        enabledModules={enabledModules}
        disabled={!canWrite}
      />
    </div>
  );
}
