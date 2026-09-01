import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { Modal } from "@/components/Modal";
import { Avatar, PageSpinner, StatusBadge } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { AppSetting, EmailTemplate, Page, Role, User } from "@/types";

const TABS = ["Company", "Users", "Roles", "Documents", "Email Templates", "System"] as const;

export default function SettingsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Company");
  const { hasPerm } = useAuth();

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Settings</h1>
      <div className="flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              "border-b-2 px-4 py-2 text-sm font-medium transition-colors",
              tab === t
                ? "border-primary-600 text-primary-600 dark:text-primary-400"
                : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Company" && <CompanyProfileTab canWrite={hasPerm("settings:write")} />}
      {tab === "Users" && <UsersTab />}
      {tab === "Roles" && <RolesTab />}
      {tab === "Documents" && <DocumentsTab canWrite={hasPerm("settings:write")} />}
      {tab === "Email Templates" && <TemplatesTab canWrite={hasPerm("settings:write")} />}
      {tab === "System" && <SystemTab />}
    </div>
  );
}

function CompanyProfileTab({ canWrite }: { canWrite: boolean }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: async () => (await api.get<AppSetting[]>("/settings")).data,
  });
  const profile = data?.find((s) => s.key === "company_profile")?.value ?? {};
  const [form, setForm] = useState<Record<string, string>>({});

  useEffect(() => {
    setForm({
      name: profile.name ?? "",
      website: profile.website ?? "",
      email: profile.email ?? "",
      phone: profile.phone ?? "",
      address: profile.address ?? "",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const save = useMutation({
    mutationFn: async () => (await api.put("/settings/company_profile", { value: form })).data,
    onSuccess: () => {
      toast("Company profile saved");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  if (isLoading) return <PageSpinner />;

  const field = (key: string, label: string, textarea = false) => (
    <div className={textarea ? "sm:col-span-2" : ""}>
      <label className="label">{label}</label>
      {textarea ? (
        <textarea rows={2} className="input" disabled={!canWrite} value={form[key] ?? ""} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
      ) : (
        <input className="input" disabled={!canWrite} value={form[key] ?? ""} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
      )}
    </div>
  );

  return (
    <div className="card max-w-3xl p-5">
      <h2 className="mb-4 font-semibold">Company Profile</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {field("name", "Company name")}
        {field("website", "Website")}
        {field("email", "Email")}
        {field("phone", "Phone")}
        {field("address", "Address", true)}
      </div>
      {canWrite && (
        <div className="mt-5 flex justify-end">
          <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save profile"}
          </button>
        </div>
      )}
      <p className="mt-4 text-xs text-slate-400">
        This information appears on quotation and invoice PDFs.
      </p>
    </div>
  );
}

function UsersTab() {
  const { hasPerm, user: me } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm] = useState({ email: "", password: "", first_name: "", last_name: "", phone: "", role_id: "" });

  const users = useQuery({
    queryKey: ["settings-users"],
    queryFn: async () => (await api.get<Page<User>>("/users", { params: { page_size: 100 } })).data,
  });
  const roles = useQuery({
    queryKey: ["settings-roles"],
    queryFn: async () => (await api.get<Role[]>("/roles")).data,
  });

  const save = useMutation({
    mutationFn: async () => {
      if (editing) {
        const { email, password, ...rest } = form;
        return (await api.patch(`/users/${editing.id}`, rest)).data;
      }
      return (await api.post("/users", form)).data;
    },
    onSuccess: () => {
      toast(editing ? "User updated" : "User created — welcome email sent");
      setModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ["settings-users"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const toggleActive = useMutation({
    mutationFn: async (u: User) =>
      u.is_active ? (await api.delete(`/users/${u.id}`)).data : (await api.patch(`/users/${u.id}`, { is_active: true })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings-users"] }),
    onError: (err) => toast(errorMessage(err), "error"),
  });

  if (users.isLoading || roles.isLoading) return <PageSpinner />;

  const canWrite = hasPerm("users:write");

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="font-semibold">Team Members</h2>
        {canWrite && (
          <button
            className="btn-primary"
            onClick={() => {
              setEditing(null);
              setForm({ email: "", password: "", first_name: "", last_name: "", phone: "", role_id: roles.data?.[0]?.id ?? "" });
              setModalOpen(true);
            }}
          >
            <Plus size={16} /> Invite User
          </button>
        )}
      </div>
      <table className="w-full">
        <thead>
          <tr>
            <th className="th">User</th>
            <th className="th">Role</th>
            <th className="th">Status</th>
            <th className="th">Last login</th>
            {canWrite && <th className="th text-right">Actions</th>}
          </tr>
        </thead>
        <tbody>
          {(users.data?.items ?? []).map((u) => (
            <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
              <td className="td">
                <span className="flex items-center gap-2">
                  <Avatar first={u.first_name} last={u.last_name} />
                  <span>
                    <span className="block font-medium">
                      {u.first_name} {u.last_name}
                    </span>
                    <span className="block text-xs text-slate-400">{u.email}</span>
                  </span>
                </span>
              </td>
              <td className="td">{u.role?.name}</td>
              <td className="td">
                <span className={`badge ${u.is_active ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300" : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"}`}>
                  {u.is_active ? "Active" : "Inactive"}
                </span>
              </td>
              <td className="td text-sm text-slate-400">{u.last_login_at ? formatDate(u.last_login_at) : "Never"}</td>
              {canWrite && (
                <td className="td text-right">
                  <button
                    className="btn-ghost !py-1 text-xs"
                    onClick={() => {
                      setEditing(u);
                      setForm({
                        email: u.email, password: "", first_name: u.first_name,
                        last_name: u.last_name, phone: u.phone ?? "", role_id: u.role.id,
                      });
                      setModalOpen(true);
                    }}
                  >
                    Edit
                  </button>
                  {u.id !== me?.id && (
                    <button className="btn-ghost !py-1 text-xs" onClick={() => toggleActive.mutate(u)}>
                      {u.is_active ? "Deactivate" : "Activate"}
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? "Edit user" : "Invite user"}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="label">First name</label>
            <input className="input" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
          </div>
          <div>
            <label className="label">Last name</label>
            <input className="input" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          </div>
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" disabled={!!editing} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          {!editing && (
            <div>
              <label className="label">Temporary password</label>
              <input className="input" type="text" placeholder="min 8 characters" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </div>
          )}
          <div>
            <label className="label">Phone</label>
            <input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          <div>
            <label className="label">Role</label>
            <select className="input" value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })}>
              {(roles.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setModalOpen(false)}>
            Cancel
          </button>
          <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </Modal>
    </div>
  );
}

function RolesTab() {
  const { hasPerm } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Role | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [perms, setPerms] = useState<Set<string>>(new Set());

  const roles = useQuery({ queryKey: ["settings-roles"], queryFn: async () => (await api.get<Role[]>("/roles")).data });
  const catalog = useQuery({
    queryKey: ["permissions-catalog"],
    queryFn: async () => (await api.get<{ modules: string[] }>("/permissions")).data,
  });

  const save = useMutation({
    mutationFn: async () => {
      const payload = { name, description, permissions: Array.from(perms) };
      if (editing) return (await api.patch(`/roles/${editing.id}`, payload)).data;
      return (await api.post("/roles", payload)).data;
    },
    onSuccess: () => {
      toast(editing ? "Role updated" : "Role created");
      setModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ["settings-roles"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  if (roles.isLoading) return <PageSpinner />;
  const canWrite = hasPerm("roles:write");
  const modules = catalog.data?.modules ?? [];

  const togglePerm = (p: string) => {
    const next = new Set(perms);
    next.has(p) ? next.delete(p) : next.add(p);
    setPerms(next);
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        {canWrite && (
          <button
            className="btn-primary"
            onClick={() => {
              setEditing(null);
              setName("");
              setDescription("");
              setPerms(new Set());
              setModalOpen(true);
            }}
          >
            <Plus size={16} /> Custom Role
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(roles.data ?? []).map((r) => (
          <div key={r.id} className="card p-4">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-semibold">{r.name}</p>
                <p className="text-xs text-slate-400">{r.description}</p>
              </div>
              {r.is_system ? (
                <span className="badge bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400">System</span>
              ) : (
                canWrite && (
                  <button
                    className="btn-ghost !py-1 text-xs"
                    onClick={() => {
                      setEditing(r);
                      setName(r.name);
                      setDescription(r.description ?? "");
                      setPerms(new Set(r.permissions));
                      setModalOpen(true);
                    }}
                  >
                    Edit
                  </button>
                )
              )}
            </div>
            <p className="mt-2 text-xs text-slate-400">
              {r.permissions.includes("*") ? "Full access" : `${r.permissions.length} permissions`}
            </p>
          </div>
        ))}
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? "Edit role" : "New custom role"} wide>
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Role name</label>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <label className="label">Description</label>
              <input className="input" value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="label">Permissions</label>
            <div className="max-h-72 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-left text-xs uppercase text-slate-400 dark:bg-slate-900">
                    <th className="px-3 py-2">Module</th>
                    {["read", "write", "delete"].map((a) => (
                      <th key={a} className="w-20 px-3 py-2 capitalize">
                        {a}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {modules.map((m) => (
                    <tr key={m} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="px-3 py-1.5 font-medium capitalize">{m}</td>
                      {["read", "write", "delete"].map((a) => (
                        <td key={a} className="px-3 py-1.5">
                          <input
                            type="checkbox"
                            className="h-4 w-4 accent-primary-600"
                            checked={perms.has(`${m}:${a}`)}
                            onChange={() => togglePerm(`${m}:${a}`)}
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setModalOpen(false)}>
              Cancel
            </button>
            <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending || !name}>
              {save.isPending ? "Saving…" : "Save role"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function DocumentTemplateCard({
  settingKey,
  heading,
  subtitle,
  extraField,
  canWrite,
  stored,
}: {
  settingKey: string;
  heading: string;
  subtitle: string;
  extraField: { key: string; label: string };
  canWrite: boolean;
  stored: Record<string, any>;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Record<string, string>>({});

  useEffect(() => {
    setForm({
      title: stored.title ?? "",
      number_prefix: stored.number_prefix ?? "",
      accent_color: stored.accent_color ?? "#4F46E5",
      footer_note: stored.footer_note ?? "",
      [extraField.key]: stored[extraField.key] ?? "",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stored]);

  const save = useMutation({
    mutationFn: async () => (await api.put(`/settings/${settingKey}`, { value: form })).data,
    onSuccess: () => {
      toast(`${heading} saved`);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const set = (key: string, value: string) => setForm((f) => ({ ...f, [key]: value }));

  return (
    <div className="card p-5">
      <h2 className="font-semibold">{heading}</h2>
      <p className="mb-4 text-xs text-slate-400">{subtitle}</p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="label">Document title</label>
          <input className="input" disabled={!canWrite} value={form.title ?? ""} onChange={(e) => set("title", e.target.value)} placeholder="e.g. TAX INVOICE" />
        </div>
        <div>
          <label className="label">Number prefix</label>
          <input className="input" disabled={!canWrite} value={form.number_prefix ?? ""} onChange={(e) => set("number_prefix", e.target.value)} placeholder="e.g. INV" />
          <p className="mt-1 text-[11px] text-slate-400">New documents will be numbered {form.number_prefix || "…"}-{new Date().getFullYear()}-0001</p>
        </div>
        <div>
          <label className="label">Accent color</label>
          <div className="flex items-center gap-2">
            <input
              type="color"
              className="h-9 w-12 cursor-pointer rounded-lg border border-slate-300 bg-white p-1 dark:border-slate-700 dark:bg-slate-900"
              disabled={!canWrite}
              value={/^#[0-9a-fA-F]{6}$/.test(form.accent_color ?? "") ? form.accent_color : "#4F46E5"}
              onChange={(e) => set("accent_color", e.target.value)}
            />
            <input className="input flex-1" disabled={!canWrite} value={form.accent_color ?? ""} onChange={(e) => set("accent_color", e.target.value)} placeholder="#4F46E5" />
          </div>
        </div>
        <div>
          <label className="label">{extraField.label}</label>
          <textarea rows={2} className="input" disabled={!canWrite} value={form[extraField.key] ?? ""} onChange={(e) => set(extraField.key, e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Footer note (shown at the bottom of the PDF)</label>
          <textarea rows={2} className="input" disabled={!canWrite} value={form.footer_note ?? ""} onChange={(e) => set("footer_note", e.target.value)} />
        </div>
      </div>
      {canWrite && (
        <div className="mt-4 flex justify-end">
          <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save template"}
          </button>
        </div>
      )}
    </div>
  );
}

function DocumentsTab({ canWrite }: { canWrite: boolean }) {
  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: async () => (await api.get<AppSetting[]>("/settings")).data,
  });

  if (isLoading) return <PageSpinner />;
  const value = (key: string) => data?.find((s) => s.key === key)?.value ?? {};

  return (
    <div className="grid max-w-6xl grid-cols-1 gap-4 xl:grid-cols-2">
      <DocumentTemplateCard
        settingKey="quotation_template"
        heading="Quotation Template"
        subtitle="Controls the quotation PDF and defaults for new quotations."
        extraField={{ key: "default_terms", label: "Default terms (used when a quotation has none)" }}
        canWrite={canWrite}
        stored={value("quotation_template")}
      />
      <DocumentTemplateCard
        settingKey="invoice_template"
        heading="Invoice Template"
        subtitle="Controls the invoice PDF and defaults for new invoices."
        extraField={{ key: "default_notes", label: "Default notes (used when an invoice has none)" }}
        canWrite={canWrite}
        stored={value("invoice_template")}
      />
      <p className="text-xs text-slate-400 xl:col-span-2">
        Company name, address, email and phone on the PDFs come from the Company tab. Changes apply to every PDF
        generated after saving; number prefixes apply to newly created documents only.
      </p>
    </div>
  );
}

function TemplatesTab({ canWrite }: { canWrite: boolean }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<EmailTemplate | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");

  const templates = useQuery({
    queryKey: ["email-templates"],
    queryFn: async () => (await api.get<EmailTemplate[]>("/settings/email-templates")).data,
  });

  const save = useMutation({
    mutationFn: async () =>
      (await api.patch(`/settings/email-templates/${editing!.id}`, { subject, body_html: body })).data,
    onSuccess: () => {
      toast("Template saved");
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["email-templates"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  if (templates.isLoading) return <PageSpinner />;

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {(templates.data ?? []).map((t) => (
        <div key={t.id} className="card p-4">
          <div className="flex items-start justify-between">
            <div>
              <p className="font-semibold capitalize">{t.name.replace(/_/g, " ")}</p>
              <p className="text-xs text-slate-400">{t.description}</p>
            </div>
            {canWrite && (
              <button
                className="btn-ghost !py-1 text-xs"
                onClick={() => {
                  setEditing(t);
                  setSubject(t.subject);
                  setBody(t.body_html);
                }}
              >
                Edit
              </button>
            )}
          </div>
          <p className="mt-2 truncate text-sm text-slate-500">{t.subject}</p>
        </div>
      ))}

      <Modal open={!!editing} onClose={() => setEditing(null)} title={`Edit template: ${editing?.name ?? ""}`} wide>
        <div className="space-y-4">
          <div>
            <label className="label">Subject</label>
            <input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} />
          </div>
          <div>
            <label className="label">Body (HTML — placeholders like {"{first_name}"} are filled at send time)</label>
            <textarea rows={8} className="input font-mono text-xs" value={body} onChange={(e) => setBody(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save template"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function SystemTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["system-status"],
    queryFn: async () => (await api.get("/settings/system-status")).data,
  });

  if (isLoading || !data) return <PageSpinner />;

  const rows = [
    { label: "Database", value: data.database, ok: true },
    { label: "SMTP email", value: data.smtp_configured ? "Configured" : "Not configured (emails log to console)", ok: data.smtp_configured },
    { label: "Redis / Celery", value: data.redis_configured ? "Configured" : "Not configured (jobs run inline)", ok: data.redis_configured },
    { label: "Meilisearch", value: data.meilisearch_configured ? "Configured" : "Not configured (SQL search fallback)", ok: data.meilisearch_configured },
    { label: "MinIO storage", value: data.minio_configured ? "Configured" : "Not configured (local disk fallback)", ok: data.minio_configured },
  ];

  return (
    <div className="card max-w-2xl divide-y divide-slate-100 dark:divide-slate-800">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between px-4 py-3">
          <span className="font-medium">{r.label}</span>
          <span className="flex items-center gap-2 text-sm text-slate-500">
            <span className={`h-2 w-2 rounded-full ${r.ok ? "bg-emerald-500" : "bg-amber-400"}`} />
            {r.value}
          </span>
        </div>
      ))}
      <p className="px-4 py-3 text-xs text-slate-400">
        Integrations are configured via backend environment variables — see backend/.env.example.
      </p>
    </div>
  );
}
