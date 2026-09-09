import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowLeft, GripVertical, Lock, Pause, Pencil, Play, Save, Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog, Modal } from "@/components/Modal";
import { Avatar } from "@/components/ui";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { ModuleBoard } from "@/platform/ModuleBoard";
import type { CrmTemplate, TenantDetail as TenantDetailType, TenantModule } from "@/types";

/** Labels for the per-module row counts the API reports. */
const COUNT_LABELS: Record<string, string> = {
  customers: "Customers",
  companies: "Companies",
  policies: "Policies",
  loans: "Loans",
  quotations: "Quotations",
  deals: "Deals",
  leads: "Leads",
  tasks: "Tasks",
};

const STATUS_STYLES: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  suspended: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  provisioning: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

function Field({ label, value, title }: { label: string; value: React.ReactNode; title?: string }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 truncate text-sm font-medium" title={title}>
        {value ?? "—"}
      </dd>
    </div>
  );
}

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
  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", plan: "", timezone: "", currency: "" });

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
      queryClient.invalidateQueries({ queryKey: ["platform", "tenant", tenantId] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const saveDetails = useMutation({
    mutationFn: async () => (await api.patch(`/platform/tenants/${tenantId}`, editForm)).data,
    onSuccess: () => {
      toast("Workspace updated");
      setEditOpen(false);
      queryClient.invalidateQueries({ queryKey: ["platform"] });
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
  const counts = Object.entries(t.record_counts ?? {});

  const patchDraft = (key: string, patch: Partial<TenantModule>) =>
    setDraft((rows) => rows.map((m) => (m.module_key === key ? { ...m, ...patch } : m)));

  const openEdit = () => {
    setEditForm({ name: t.name, plan: t.plan, timezone: t.timezone, currency: t.currency });
    setEditOpen(true);
  };

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <Link to="/platform" className="mb-2 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-primary-600">
          <ArrowLeft size={15} /> All tenants
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold">
              {t.name}
              <span className={clsx("badge", STATUS_STYLES[t.status] ?? STATUS_STYLES.provisioning)}>
                {t.status}
              </span>
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              /{t.slug} · {templateName} · created {formatDate(t.created_at)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-secondary" onClick={openEdit}>
              <Pencil size={15} /> Edit
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
        <h2 className="mb-4 font-semibold">Workspace</h2>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-4">
          <Field label="Owner" value={t.owner_name} title={t.owner_email ?? undefined} />
          <Field
            label="Owner email"
            value={
              t.owner_email ? (
                <a className="text-primary-600 hover:underline dark:text-primary-400" href={`mailto:${t.owner_email}`}>
                  {t.owner_email}
                </a>
              ) : null
            }
            title={t.owner_email ?? undefined}
          />
          <Field label="Plan" value={t.plan} />
          <Field label="Type" value={t.type} />
          <Field label="Template" value={templateName} title={t.template_key} />
          <Field label="Timezone" value={t.timezone} />
          <Field label="Currency" value={t.currency} />
          <Field label="Modules" value={`${t.enabled_module_count} of ${t.module_count} on`} />
        </dl>

        {counts.length > 0 && (
          <>
            <h3 className="mb-3 mt-6 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              What is in this workspace
            </h3>
            <dl className="grid grid-cols-3 gap-3 sm:grid-cols-5">
              {counts.map(([key, value]) => (
                <div key={key} className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
                  <dt className="text-[11px] font-medium text-slate-400">{COUNT_LABELS[key] ?? key}</dt>
                  <dd className="text-lg font-bold tabular-nums">{value}</dd>
                </div>
              ))}
            </dl>
          </>
        )}
      </section>

      <section className="card p-5">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-semibold">Users</h2>
          <span className="text-sm text-slate-400">
            {t.user_count} user{t.user_count === 1 ? "" : "s"}
          </span>
        </div>
        <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">
          Sign-ins that belong to this workspace. The console cannot open their CRM — to
          look at their data, ask them to share it, or add yourself as one of their users
          from inside the workspace.
        </p>
        <div className="table-scroll -mx-5 overflow-x-auto px-5">
          <table className="w-full">
            <thead>
              <tr>
                <th className="th">Name</th>
                <th className="th">Email</th>
                <th className="th">Role</th>
                <th className="th">Last sign-in</th>
              </tr>
            </thead>
            <tbody>
              {(t.users ?? []).map((u) => (
                <tr
                  key={u.id}
                  className="transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                >
                  <td className="td">
                    <span className="flex items-center gap-2">
                      <Avatar first={u.full_name.split(" ")[0]} last={u.full_name.split(" ")[1] ?? ""} size={24} />
                      <span>{u.full_name || "—"}</span>
                      {u.is_owner && (
                        <span className="badge bg-primary-50 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">
                          owner
                        </span>
                      )}
                      {!u.is_active && (
                        <span className="badge bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                          inactive
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="td text-slate-500 dark:text-slate-400">{u.email}</td>
                  <td className="td">{u.role ?? "—"}</td>
                  <td className="td text-slate-500 dark:text-slate-400">
                    {u.last_login_at ? formatDateTime(u.last_login_at) : "never"}
                  </td>
                </tr>
              ))}
              {(t.users ?? []).length === 0 && (
                <tr>
                  <td colSpan={4} className="py-10 text-center text-sm text-slate-400">
                    No users yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-semibold">Modules</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              What this client sees in their sidebar, and what each module is called for them.
              Switching one off refuses it at the API as well, so it is gone rather than hidden.
            </p>
          </div>
          <button
            className="btn-primary ml-auto shrink-0"
            disabled={!dirty || saveModules.isPending}
            onClick={() => saveModules.mutate()}
          >
            <Save size={15} /> {saveModules.isPending ? "Saving…" : dirty ? "Save changes" : "Saved"}
          </button>
        </div>

        {/* The same board the template editor uses. A workspace's modules and a
            template's modules are the same decision at two moments, so they should
            not be two different screens to learn. */}
        <ModuleBoard
          catalog={draft.map((m) => ({
            key: m.module_key,
            label: m.label,
            order: m.order,
            icon: m.icon,
            locked: m.locked,
          }))}
          value={draft.map((m) => ({
            key: m.module_key,
            enabled: m.enabled,
            label: m.label,
            order: m.order,
          }))}
          onChange={(next) => {
            const byKey = new Map(draft.map((m) => [m.module_key, m]));
            setDraft(
              next.map((m, index) => ({
                ...byKey.get(m.key)!,
                label: m.label ?? byKey.get(m.key)!.label,
                enabled: m.enabled,
                order: index + 1,
              }))
            );
          }}
        />
      </section>

      <section className="card border-red-200 p-5 dark:border-red-900/60">
        <h2 className="font-semibold text-red-700 dark:text-red-400">Delete this tenant</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Their users lose access immediately and the workspace disappears from the console.
          The data is retained for 30 days before it is purged, so this can be undone by
          contacting support within that window — but not from here.
        </p>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          Their email addresses are released straight away, so the same client can be added
          back under the same address. Suspending is usually what you want instead: it blocks
          sign-in and keeps everything intact.
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

      <Modal open={editOpen} onClose={() => setEditOpen(false)} title={`Edit ${t.name}`}>
        <div className="space-y-4">
          <div>
            <label className="label">Workspace name</label>
            <input
              className="input"
              value={editForm.name}
              onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
              autoFocus
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className="label">Plan</label>
              <input
                className="input"
                value={editForm.plan}
                onChange={(e) => setEditForm((f) => ({ ...f, plan: e.target.value }))}
              />
            </div>
            <div>
              <label className="label">Timezone</label>
              <input
                className="input"
                value={editForm.timezone}
                onChange={(e) => setEditForm((f) => ({ ...f, timezone: e.target.value }))}
              />
            </div>
            <div>
              <label className="label">Currency</label>
              <input
                className="input"
                value={editForm.currency}
                onChange={(e) => setEditForm((f) => ({ ...f, currency: e.target.value }))}
              />
            </div>
          </div>
          <p className="text-xs text-slate-400">
            The slug and template are fixed once a workspace exists — both are baked into
            the data it already holds.
          </p>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setEditOpen(false)}>
              Cancel
            </button>
            <button
              className="btn-primary"
              disabled={editForm.name.trim().length < 2 || saveDetails.isPending}
              onClick={() => saveDetails.mutate()}
            >
              {saveDetails.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </Modal>

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
