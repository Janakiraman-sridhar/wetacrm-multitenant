import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Building2, ChevronRight, Plus, Search, User as UserIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Modal } from "@/components/Modal";
import { DeletedTenants } from "@/platform/DeletedTenants";
import { Select } from "@/components/Select";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CrmTemplate, PlatformStats, Tenant, TenantDetail } from "@/types";

const STATUS_STYLES: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  trial: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  suspended: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  provisioning: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  deleted: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

export default function Tenants() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const tenants = useQuery({
    queryKey: ["platform", "tenants"],
    queryFn: async () => (await api.get<Tenant[]>("/platform/tenants")).data,
  });
  const stats = useQuery({
    queryKey: ["platform", "stats"],
    queryFn: async () => (await api.get<PlatformStats>("/platform/stats")).data,
  });
  const templates = useQuery({
    queryKey: ["platform", "templates"],
    queryFn: async () => (await api.get<CrmTemplate[]>("/platform/templates")).data,
  });

  const [form, setForm] = useState({
    name: "",
    type: "company",
    template_key: "general_crm",
    owner_first_name: "",
    owner_last_name: "",
    owner_email: "",
    owner_password: "",
  });

  const createTenant = useMutation({
    mutationFn: async () => (await api.post<TenantDetail>("/platform/tenants", form)).data,
    onSuccess: (tenant) => {
      toast(`${tenant.name} created`);
      setCreateOpen(false);
      setForm({
        name: "", type: "company", template_key: "general_crm",
        owner_first_name: "", owner_last_name: "", owner_email: "", owner_password: "",
      });
      queryClient.invalidateQueries({ queryKey: ["platform"] });
      navigate(`/platform/tenants/${tenant.id}`);
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const rows = useMemo(() => {
    const list = tenants.data ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (t) => t.name.toLowerCase().includes(q) || t.slug.toLowerCase().includes(q)
    );
  }, [tenants.data, search]);

  const templateOptions = (templates.data ?? []).map((t) => ({ value: t.key, label: t.name }));
  const templateName = (key: string) =>
    templates.data?.find((t) => t.key === key)?.name ?? key;

  const canSubmit =
    form.name.trim().length >= 2 &&
    form.owner_email.includes("@") &&
    (form.owner_password === "" || form.owner_password.length >= 8);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Tenants</h1>
          <p className="max-w-3xl text-sm text-slate-500 dark:text-slate-400">
            Each tenant is one client workspace with its own isolated data. You provision
            and shape a workspace from here — its modules, template and status — but you
            cannot go inside it: a platform account has no route into a client's records.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input w-56 !pl-8"
              placeholder="Search tenants…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button className="btn-primary" onClick={() => setCreateOpen(true)}>
            <Plus size={16} /> New tenant
          </button>
        </div>
      </div>

      {stats.data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Tenants" value={stats.data.tenants_total} />
          <StatCard label="Active" value={stats.data.tenants_active} />
          <StatCard label="Suspended" value={stats.data.tenants_suspended} />
          <StatCard label="Users" value={stats.data.users_total} />
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left dark:border-slate-800 dark:bg-slate-900/60">
              <tr className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <th className="px-4 py-3">Workspace</th>
                <th className="px-4 py-3">Template</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tenants.isLoading && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400">Loading…</td></tr>
              )}
              {!tenants.isLoading && rows.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400">No tenants yet.</td></tr>
              )}
              {rows.map((tenant) => (
                <tr
                  key={tenant.id}
                  className="cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50 dark:border-slate-800/70 dark:hover:bg-slate-800/40"
                  onClick={() => navigate(`/platform/tenants/${tenant.id}`)}
                >
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-2.5">
                      <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary-50 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300">
                        {tenant.type === "individual" ? <UserIcon size={15} /> : <Building2 size={15} />}
                      </span>
                      <span>
                        <span className="block font-medium">{tenant.name}</span>
                        <span className="block text-xs text-slate-400">/{tenant.slug}</span>
                      </span>
                    </span>
                  </td>
                  <td className="px-4 py-3">{templateName(tenant.template_key)}</td>
                  <td className="px-4 py-3">
                    <span className={clsx("badge", STATUS_STYLES[tenant.status] ?? STATUS_STYLES.provisioning)}>
                      {tenant.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{formatDate(tenant.created_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`/platform/tenants/${tenant.id}`}
                      className="btn-secondary !py-1.5"
                      onClick={(e) => e.stopPropagation()}
                      title="Owner, users, modules and record counts for this workspace"
                    >
                      Manage <ChevronRight size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <DeletedTenants />

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New tenant" wide>
        <div className="space-y-5">
          <div>
            <div className="mb-3 flex items-center gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
                Workspace
              </span>
              <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="label">Client name</label>
                <input
                  className="input"
                  placeholder="e.g. Sunrise Insurance Agency"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  autoFocus
                />
              </div>
              <div>
                <label className="label">Type</label>
                <Select
                  value={form.type}
                  onChange={(v) => setForm({ ...form, type: v })}
                  options={[
                    { value: "company", label: "Company / agency" },
                    { value: "individual", label: "Individual agent" },
                  ]}
                />
              </div>
              <div>
                <label className="label">Template</label>
                <Select
                  value={form.template_key}
                  onChange={(v) => setForm({ ...form, template_key: v })}
                  options={templateOptions}
                  placeholder="Choose a template…"
                />
                <p className="mt-1 text-xs text-slate-400">
                  Decides which modules they get and what those modules are called.
                </p>
              </div>
            </div>
          </div>

          <div>
            <div className="mb-3 flex items-center gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
                Owner account
              </span>
              <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="label">First name</label>
                <input
                  className="input"
                  value={form.owner_first_name}
                  onChange={(e) => setForm({ ...form, owner_first_name: e.target.value })}
                />
              </div>
              <div>
                <label className="label">Last name</label>
                <input
                  className="input"
                  value={form.owner_last_name}
                  onChange={(e) => setForm({ ...form, owner_last_name: e.target.value })}
                />
              </div>
              <div className="sm:col-span-2">
                <label className="label">Email</label>
                <input
                  className="input"
                  type="email"
                  placeholder="owner@agency.com"
                  value={form.owner_email}
                  onChange={(e) => setForm({ ...form, owner_email: e.target.value })}
                />
                <p className="mt-1 text-xs text-slate-400">
                  Must be unique across the whole platform — one login belongs to one workspace.
                </p>
              </div>
              <div className="sm:col-span-2">
                <label className="label">Initial password</label>
                <input
                  className="input"
                  type="text"
                  placeholder="At least 8 characters"
                  value={form.owner_password}
                  onChange={(e) => setForm({ ...form, owner_password: e.target.value })}
                />
                <p className="mt-1 text-xs text-slate-400">
                  Share it with the client and have them change it on first sign-in.
                </p>
              </div>
            </div>
          </div>

          <div className="-mx-5 -mb-5 flex justify-end gap-2 border-t border-slate-200 bg-slate-50/60 px-5 py-3.5 dark:border-slate-800 dark:bg-slate-900/60">
            <button className="btn-secondary" onClick={() => setCreateOpen(false)}>Cancel</button>
            <button
              className="btn-primary"
              disabled={!canSubmit || createTenant.isPending}
              onClick={() => createTenant.mutate()}
            >
              {createTenant.isPending ? "Creating…" : "Create tenant"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
