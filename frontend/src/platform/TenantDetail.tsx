import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, GripVertical, LogIn, Lock, Pause, Play, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog, Modal } from "@/components/Modal";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { moduleIcon } from "@/lib/modules";
import { useOpenWorkspace } from "@/platform/useImpersonation";
import type { CrmTemplate, TenantDetail as TenantDetailType, TenantModule } from "@/types";

export default function TenantDetail() {
  const { tenantId = "" } = useParams();
  const { toast } = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<TenantModule[]>([]);
  const [confirmSuspend, setConfirmSuspend] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  // Typing the name is the guard: a delete is not something to reach by mis-click.
  const [confirmName, setConfirmName] = useState("");

  const tenant = useQuery({
    queryKey: ["platform", "tenant", tenantId],
    queryFn: async () => (await api.get<TenantDetailType>(`/platform/tenants/${tenantId}`)).data,
  });
  const modules = useQuery({
    queryKey: ["platform", "tenant", tenantId, "modules"],
    queryFn: async () => (await api.get<TenantModule[]>(`/platform/tenants/${tenantId}/modules`)).data,
  });
  const templates = useQuery({
    queryKey: ["platform", "templates"],
    queryFn: async () => (await api.get<CrmTemplate[]>("/platform/templates")).data,
  });

  useEffect(() => {
    if (modules.data) setDraft(modules.data);
  }, [modules.data]);

  const dirty =
    !!modules.data &&
    JSON.stringify(modules.data.map((m) => [m.module_key, m.label, m.enabled])) !==
      JSON.stringify(draft.map((m) => [m.module_key, m.label, m.enabled]));

  const saveModules = useMutation({
    mutationFn: async () =>
      (
        await api.patch(
          `/platform/tenants/${tenantId}/modules`,
          draft.map((m) => ({ module_key: m.module_key, label: m.label, enabled: m.enabled, order: m.order }))
        )
      ).data,
    onSuccess: () => {
      toast("Modules updated");
      queryClient.invalidateQueries({ queryKey: ["platform", "tenant", tenantId, "modules"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const setStatus = useMutation({
    mutationFn: async (action: "suspend" | "reactivate") =>
      (await api.post(`/platform/tenants/${tenantId}/${action}`, {})).data,
    onSuccess: (_data, action) => {
      toast(action === "suspend" ? "Tenant suspended" : "Tenant reactivated");
      setConfirmSuspend(false);
      queryClient.invalidateQueries({ queryKey: ["platform"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const openWorkspace = useOpenWorkspace();

  const removeTenant = useMutation({
    mutationFn: async () => (await api.delete(`/platform/tenants/${tenantId}`)).data,
    onSuccess: () => {
      toast("Tenant deleted");
      queryClient.invalidateQueries({ queryKey: ["platform"] });
      navigate("/platform");
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  if (tenant.isLoading) return <p className="text-slate-400">Loading…</p>;
  if (!tenant.data) return <p className="text-slate-400">Tenant not found.</p>;

  const t = tenant.data;
  const templateName = templates.data?.find((x) => x.key === t.template_key)?.name ?? t.template_key;
  const enabledCount = draft.filter((m) => m.enabled).length;

  const patchDraft = (key: string, patch: Partial<TenantModule>) =>
    setDraft((rows) => rows.map((m) => (m.module_key === key ? { ...m, ...patch } : m)));

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <Link to="/platform" className="mb-2 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-primary-600">
          <ArrowLeft size={15} /> All tenants
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{t.name}</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              /{t.slug} · {templateName} · {t.user_count} user{t.user_count === 1 ? "" : "s"} · created {formatDate(t.created_at)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="btn-primary"
              disabled={openWorkspace.isPending || t.status === "suspended"}
              onClick={() => openWorkspace.mutate(tenantId)}
              title={
                t.status === "suspended"
                  ? "Reactivate this workspace before opening it"
                  : "Sign in to this workspace as one of its users. Time-limited and audited."
              }
            >
              <LogIn size={15} /> {openWorkspace.isPending ? "Opening…" : "Open workspace"}
            </button>
            {t.status === "suspended" ? (
              <button className="btn-primary" onClick={() => setStatus.mutate("reactivate")}>
                <Play size={15} /> Reactivate
              </button>
            ) : (
              <button className="btn-secondary !text-amber-700" onClick={() => setConfirmSuspend(true)}>
                <Pause size={15} /> Suspend
              </button>
            )}
          </div>
        </div>
      </div>

      {t.status === "suspended" && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          This workspace is suspended. Its users cannot sign in; the data is retained.
        </div>
      )}

      <section className="card p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-semibold">Modules</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              What this client sees in their sidebar, and what each module is called for them.
              {" "}
              <span className="text-slate-400">{enabledCount} of {draft.length} enabled.</span>
            </p>
          </div>
          <button
            className="btn-primary"
            disabled={!dirty || saveModules.isPending}
            onClick={() => saveModules.mutate()}
          >
            <Save size={15} /> {saveModules.isPending ? "Saving…" : "Save changes"}
          </button>
        </div>

        <div className="divide-y divide-slate-100 dark:divide-slate-800">
          {draft.map((m) => {
            const Icon = moduleIcon(m.icon);
            return (
              <div key={m.module_key} className="flex items-center gap-3 py-2.5">
                <GripVertical size={15} className="shrink-0 text-slate-300" />
                <Icon size={16} className="shrink-0 text-primary-600 dark:text-primary-400" />
                <span className="w-32 shrink-0 truncate text-xs text-slate-400" title={m.module_key}>
                  {m.module_key}
                </span>
                <input
                  className="input !py-1.5 flex-1"
                  value={m.label}
                  onChange={(e) => patchDraft(m.module_key, { label: e.target.value })}
                  aria-label={`Label for ${m.module_key}`}
                />
                <label
                  className={clsx(
                    "flex shrink-0 items-center gap-2 text-sm",
                    m.locked ? "cursor-not-allowed text-slate-400" : "cursor-pointer"
                  )}
                  title={m.locked ? "This module cannot be switched off" : undefined}
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-primary-600"
                    checked={m.enabled}
                    disabled={m.locked}
                    onChange={(e) => patchDraft(m.module_key, { enabled: e.target.checked })}
                  />
                  {m.locked ? <Lock size={13} /> : "On"}
                </label>
              </div>
            );
          })}
          {draft.length === 0 && <p className="py-6 text-center text-sm text-slate-400">No modules configured.</p>}
        </div>
      </section>

      <section className="card border-red-200 p-5 dark:border-red-900/60">
        <h2 className="font-semibold text-red-700 dark:text-red-400">Delete this tenant</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Their users lose access immediately and the workspace disappears from the console.
          The data is retained for 30 days before it is purged, so this can be undone by
          contacting support within that window — but not from here.
        </p>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          Suspending is usually what you want: it blocks sign-in and keeps everything intact.
        </p>
        <button
          className="btn-danger mt-3"
          disabled={removeTenant.isPending}
          onClick={() => {
            setConfirmName("");
            setConfirmDelete(true);
          }}
        >
          <Trash2 size={15} /> Delete {t.name}
        </button>
      </section>

      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title={`Delete ${t.name}?`}>
        <div className="space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            This removes the workspace and signs out its {t.user_count} user
            {t.user_count === 1 ? "" : "s"}. Type the workspace name to confirm.
          </p>
          <div>
            <label className="label">Workspace name</label>
            <input
              className="input"
              placeholder={t.name}
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setConfirmDelete(false)}>
              Cancel
            </button>
            <button
              className="btn-danger"
              disabled={confirmName.trim() !== t.name || removeTenant.isPending}
              onClick={() => removeTenant.mutate()}
            >
              {removeTenant.isPending ? "Deleting…" : "Delete permanently"}
            </button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmSuspend}
        onClose={() => setConfirmSuspend(false)}
        onConfirm={() => setStatus.mutate("suspend")}
        title={`Suspend ${t.name}?`}
        message="Their users will not be able to sign in. Nothing is deleted and you can reactivate at any time."
        busy={setStatus.isPending}
      />
    </div>
  );
}
