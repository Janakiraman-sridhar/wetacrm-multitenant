import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ExternalLink, Loader2, Plus, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Modal } from "@/components/Modal";
import { Select } from "@/components/Select";
import { Avatar, PageSpinner, StatusBadge } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { API_URL, api, errorMessage, tokenStore } from "@/lib/api";
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

function CompanyLogo({ canWrite }: { canWrite: boolean }) {
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadLogo = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/settings/company-logo`, {
        headers: { Authorization: `Bearer ${tokenStore.access}` },
      });
      if (!res.ok) {
        setLogoUrl(null);
        return;
      }
      setLogoUrl(URL.createObjectURL(await res.blob()));
    } catch {
      setLogoUrl(null);
    }
  };

  useEffect(() => {
    loadLogo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const upload = async (file: File) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.post("/settings/company-logo", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast("Logo uploaded");
      await loadLogo();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.delete("/settings/company-logo");
      setLogoUrl(null);
      toast("Logo removed");
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-5 border-t border-slate-100 pt-4 dark:border-slate-800">
      <label className="label">Company logo</label>
      <div className="flex flex-wrap items-center gap-4">
        {logoUrl ? (
          <img src={logoUrl} alt="Company logo" className="h-16 max-w-48 rounded-lg border border-slate-200 bg-white object-contain p-1.5 dark:border-slate-700" />
        ) : (
          <div className="flex h-16 w-32 items-center justify-center rounded-lg border border-dashed border-slate-300 text-xs text-slate-400 dark:border-slate-700">
            No logo yet
          </div>
        )}
        {canWrite && (
          <div className="flex gap-2">
            <button className="btn-secondary" disabled={busy} onClick={() => fileRef.current?.click()}>
              <Upload size={15} /> {logoUrl ? "Replace" : "Upload"}
            </button>
            {logoUrl && (
              <button className="btn-ghost text-red-500" disabled={busy} onClick={remove}>
                <Trash2 size={15} /> Remove
              </button>
            )}
          </div>
        )}
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
            e.target.value = "";
          }}
        />
      </div>
      <p className="mt-1.5 text-xs text-slate-400">Shown on quotation and invoice PDFs. PNG, JPEG or WebP, up to 2 MB.</p>
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
      <CompanyLogo canWrite={canWrite} />
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

const FONT_OPTIONS = [
  { value: "helvetica", label: "Helvetica (sans-serif)" },
  { value: "times", label: "Times (serif)" },
];

const ACCENT_PRESETS = ["#4F46E5", "#0E7490", "#059669", "#D97706", "#DC2626", "#7C3AED", "#0F172A"];

const TEMPLATE_DEFAULTS: Record<string, any> = {
  title: "",
  number_prefix: "",
  accent_color: "#4F46E5",
  layout: "modern",
  font: "helvetica",
  label_item: "Item & Description",
  label_quantity: "Qty",
  label_rate: "Rate",
  label_tax: "Tax %",
  label_amount: "Amount",
  show_tax_column: true,
  show_signature: true,
  show_logo: true,
  signature_label: "Authorized Signatory",
  bank_details: "",
  footer_note: "",
};

function templateForm(stored: Record<string, any>, extraKey: string): Record<string, any> {
  return {
    ...TEMPLATE_DEFAULTS,
    ...Object.fromEntries(Object.entries(stored).filter(([, v]) => v !== undefined && v !== null)),
    [extraKey]: stored[extraKey] ?? "",
  };
}

function DocSectionHeader({ title }: { title: string }) {
  return (
    <div className="flex items-center gap-3 pt-1">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
        {title}
      </span>
      <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
    </div>
  );
}

function Switch({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <label className={clsx("flex items-center justify-between gap-3 py-1 text-sm", disabled ? "opacity-60" : "cursor-pointer")}>
      {label}
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={clsx(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors",
          checked ? "bg-primary-600" : "bg-slate-300 dark:bg-slate-700"
        )}
        role="switch"
        aria-checked={checked}
      >
        <span
          className={clsx(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all",
            checked ? "left-[18px]" : "left-0.5"
          )}
        />
      </button>
    </label>
  );
}

/** Miniature document thumbnails used as the layout picker. */
function LayoutPicker({
  value,
  onChange,
  accent,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  accent: string;
  disabled?: boolean;
}) {
  const safeAccent = /^#[0-9a-fA-F]{6}$/.test(accent) ? accent : "#4F46E5";
  const options = [
    { key: "modern", label: "Modern" },
    { key: "classic", label: "Classic" },
    { key: "minimal", label: "Minimal" },
  ];
  return (
    <div className="grid grid-cols-3 gap-2.5">
      {options.map((opt) => (
        <button
          key={opt.key}
          type="button"
          disabled={disabled}
          onClick={() => onChange(opt.key)}
          className={clsx(
            "rounded-xl border p-2.5 transition-all",
            value === opt.key
              ? "border-primary-400 ring-2 ring-primary-500/30 dark:border-primary-600"
              : "border-slate-200 hover:border-slate-300 dark:border-slate-700 dark:hover:border-slate-600"
          )}
        >
          {/* mini document */}
          <div className="rounded-md border border-slate-200 bg-white p-1.5 dark:border-slate-600 dark:bg-slate-800">
            <div className="mb-1 flex items-center justify-between">
              <span className="h-1.5 w-4 rounded-sm bg-slate-300 dark:bg-slate-500" />
              <span className="h-1.5 w-6 rounded-sm" style={{ background: safeAccent }} />
            </div>
            {opt.key === "modern" && <div className="h-2 rounded-sm" style={{ background: safeAccent }} />}
            {opt.key === "classic" && <div className="h-2 border-y-2 border-slate-700 dark:border-slate-300" />}
            {opt.key === "minimal" && <div className="h-2 border-b-2" style={{ borderColor: safeAccent }} />}
            <div className="mt-1 space-y-1">
              <div className={clsx("h-1 rounded-sm", opt.key === "modern" ? "bg-slate-100 dark:bg-slate-700" : "bg-transparent")} />
              <div className="h-px bg-slate-200 dark:bg-slate-600" />
              <div className="h-px bg-slate-200 dark:bg-slate-600" />
            </div>
          </div>
          <p className={clsx("mt-1.5 text-center text-xs font-medium", value === opt.key ? "text-primary-600 dark:text-primary-400" : "text-slate-500")}>
            {opt.label}
          </p>
        </button>
      ))}
    </div>
  );
}

function AccentPicker({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {ACCENT_PRESETS.map((c) => (
        <button
          key={c}
          type="button"
          disabled={disabled}
          onClick={() => onChange(c)}
          className={clsx(
            "h-7 w-7 rounded-full border-2 transition-transform hover:scale-110",
            value.toLowerCase() === c.toLowerCase() ? "border-slate-700 dark:border-white" : "border-transparent"
          )}
          style={{ background: c }}
          title={c}
        />
      ))}
      <label className="relative ml-1 flex h-7 w-7 cursor-pointer items-center justify-center overflow-hidden rounded-full border border-dashed border-slate-300 text-[10px] font-semibold text-slate-400 hover:border-slate-400 dark:border-slate-600">
        +
        <input
          type="color"
          className="absolute inset-0 cursor-pointer opacity-0"
          disabled={disabled}
          value={/^#[0-9a-fA-F]{6}$/.test(value) ? value : "#4F46E5"}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
      <span className="text-xs uppercase tabular-nums text-slate-400">{value}</span>
    </div>
  );
}

function DocumentsTab({ canWrite }: { canWrite: boolean }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<"quotation" | "invoice">("quotation");
  const [forms, setForms] = useState<Record<string, Record<string, any>> | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: async () => (await api.get<AppSetting[]>("/settings")).data,
  });

  const stored = useMemo(() => {
    const value = (key: string) => data?.find((s) => s.key === key)?.value ?? {};
    return {
      quotation: value("quotation_template"),
      invoice: value("invoice_template"),
    };
  }, [data]);

  useEffect(() => {
    if (data && !forms) {
      setForms({
        quotation: templateForm(stored.quotation, "default_terms"),
        invoice: templateForm(stored.invoice, "default_notes"),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const form = forms?.[kind];
  const extraKey = kind === "quotation" ? "default_terms" : "default_notes";
  const extraLabel = kind === "quotation" ? "Default terms for new quotations" : "Default notes for new invoices";
  const dirty = !!form && JSON.stringify(form) !== JSON.stringify(templateForm(stored[kind], extraKey));

  const set = (key: string, value: any) =>
    setForms((f) => (f ? { ...f, [kind]: { ...f[kind], [key]: value } } : f));

  // Debounced live preview: re-render the sample PDF as settings change.
  useEffect(() => {
    if (!form) return;
    let cancelled = false;
    setPreviewLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/settings/document-preview/${kind}`, {
          method: "POST",
          headers: { Authorization: `Bearer ${tokenStore.access}`, "Content-Type": "application/json" },
          body: JSON.stringify({ value: form }),
        });
        if (!res.ok) throw new Error();
        const url = URL.createObjectURL(await res.blob());
        if (!cancelled) {
          setPreviewUrl((old) => {
            if (old) URL.revokeObjectURL(old);
            return url;
          });
        }
      } catch {
        /* keep the last good preview */
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(form), kind]);

  const save = useMutation({
    mutationFn: async () => (await api.put(`/settings/${kind}_template`, { value: form })).data,
    onSuccess: () => {
      toast(`${kind === "quotation" ? "Quotation" : "Invoice"} template saved`);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  if (isLoading || !form) return <PageSpinner />;

  return (
    <div className="space-y-4">
      {/* Document switcher + save */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-slate-700 dark:bg-slate-800">
          {(["quotation", "invoice"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={clsx(
                "rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-colors",
                kind === k
                  ? "bg-white text-primary-700 shadow-sm dark:bg-slate-900 dark:text-primary-300"
                  : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
              )}
            >
              {k} template
            </button>
          ))}
        </div>
        {canWrite && (
          <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending || !dirty}>
            {save.isPending ? "Saving…" : dirty ? "Save changes" : "Saved"}
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        {/* Editor */}
        <div className="card space-y-5 self-start p-5">
          <DocSectionHeader title="Style" />
          <div>
            <label className="label">Layout</label>
            <LayoutPicker value={form.layout} onChange={(v) => set("layout", v)} accent={form.accent_color} disabled={!canWrite} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Font</label>
              <Select value={form.font} onChange={(v) => set("font", v)} options={FONT_OPTIONS} clearable={false} searchable={false} />
            </div>
            <div>
              <label className="label">Accent color</label>
              <AccentPicker value={form.accent_color} onChange={(v) => set("accent_color", v)} disabled={!canWrite} />
            </div>
          </div>

          <DocSectionHeader title="Header" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Document title</label>
              <input className="input" disabled={!canWrite} value={form.title} onChange={(e) => set("title", e.target.value)} placeholder={kind === "quotation" ? "QUOTATION" : "TAX INVOICE"} />
            </div>
            <div>
              <label className="label">Number prefix</label>
              <input className="input" disabled={!canWrite} value={form.number_prefix} onChange={(e) => set("number_prefix", e.target.value)} placeholder={kind === "quotation" ? "QT" : "INV"} />
              <p className="mt-1 text-[11px] text-slate-400">
                e.g. {(form.number_prefix || (kind === "quotation" ? "QT" : "INV")).toUpperCase()}-{new Date().getFullYear()}-0001 (new documents only)
              </p>
            </div>
          </div>
          <Switch label="Show company logo (uploaded in the Company tab)" checked={!!form.show_logo} onChange={(v) => set("show_logo", v)} disabled={!canWrite} />

          <DocSectionHeader title="Item table" />
          <div>
            <label className="label">Column labels</label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {(
                [
                  ["label_item", "Item"],
                  ["label_quantity", "Qty"],
                  ["label_rate", "Rate"],
                  ["label_tax", "Tax"],
                  ["label_amount", "Amount"],
                ] as const
              ).map(([key, ph]) => (
                <input key={key} className="input !py-1.5 text-sm" disabled={!canWrite} placeholder={ph} value={form[key]} onChange={(e) => set(key, e.target.value)} />
              ))}
            </div>
          </div>
          <Switch label="Show tax column" checked={!!form.show_tax_column} onChange={(v) => set("show_tax_column", v)} disabled={!canWrite} />

          <DocSectionHeader title="Footer" />
          <div>
            <label className="label">Payment / bank details</label>
            <textarea rows={3} className="input font-mono text-xs" disabled={!canWrite} placeholder={"Bank: HDFC Bank\nA/c No: 1234567890\nIFSC: HDFC0001234"} value={form.bank_details} onChange={(e) => set("bank_details", e.target.value)} />
          </div>
          <Switch label="Show authorized-signatory block" checked={!!form.show_signature} onChange={(v) => set("show_signature", v)} disabled={!canWrite} />
          {form.show_signature && (
            <div>
              <label className="label">Signature label</label>
              <input className="input" disabled={!canWrite} value={form.signature_label} onChange={(e) => set("signature_label", e.target.value)} />
            </div>
          )}
          <div>
            <label className="label">Footer note</label>
            <input className="input" disabled={!canWrite} value={form.footer_note} onChange={(e) => set("footer_note", e.target.value)} placeholder="Thank you for your business." />
          </div>
          <div>
            <label className="label">{extraLabel}</label>
            <textarea rows={2} className="input" disabled={!canWrite} value={form[extraKey]} onChange={(e) => set(extraKey, e.target.value)} />
          </div>
        </div>

        {/* Live preview */}
        <div className="card sticky top-0 flex h-[calc(100vh-220px)] min-h-[480px] flex-col self-start overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5 dark:border-slate-800">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              Live preview
              {previewLoading && <Loader2 size={13} className="animate-spin text-primary-500" />}
            </h3>
            <button
              className="btn-ghost !px-2 !py-1 text-xs text-slate-400 hover:text-primary-600"
              onClick={() => previewUrl && window.open(previewUrl, "_blank")}
              disabled={!previewUrl}
              title="Open the preview in a new tab"
            >
              <ExternalLink size={13} /> Open
            </button>
          </div>
          <div className="flex-1 bg-slate-100 dark:bg-slate-800">
            {previewUrl ? (
              <iframe title="Template preview" src={`${previewUrl}#toolbar=0&navpanes=0`} className="h-full w-full" />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-slate-400">Rendering preview…</div>
            )}
          </div>
          <p className="border-t border-slate-200 px-4 py-2 text-[11px] text-slate-400 dark:border-slate-800">
            Rendered with sample data and your unsaved changes — exactly what customers will receive.
          </p>
        </div>
      </div>
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
