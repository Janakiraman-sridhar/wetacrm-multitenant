import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Copy, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog, Modal } from "@/components/Modal";
import { Select } from "@/components/Select";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { TemplateEditor } from "@/platform/TemplateEditor";
import type { CrmTemplate, CrmTemplateDetail } from "@/types";

/** "Agency Lite" becomes "agency_lite" — mirrors the key pattern the API enforces. */
function slugify(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

export default function Templates() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [cloning, setCloning] = useState<CrmTemplate | null>(null);
  const [inspecting, setInspecting] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [cloneForm, setCloneForm] = useState({ key: "", name: "", description: "" });
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<CrmTemplate | null>(null);
  const [newForm, setNewForm] = useState({
    key: "", name: "", description: "", base_key: "general_crm",
  });

  const templates = useQuery({
    queryKey: ["platform", "templates"],
    queryFn: async () => (await api.get<CrmTemplate[]>("/platform/templates")).data,
  });

  const detail = useQuery({
    queryKey: ["platform", "template", inspecting],
    queryFn: async () => (await api.get<CrmTemplateDetail>(`/platform/templates/${inspecting}`)).data,
    enabled: !!inspecting,
  });

  const clone = useMutation({
    mutationFn: async () =>
      (await api.post(`/platform/templates/${cloning!.key}/clone`, cloneForm)).data,
    onSuccess: () => {
      toast("Template cloned");
      setCloning(null);
      setCloneForm({ key: "", name: "", description: "" });
      queryClient.invalidateQueries({ queryKey: ["platform", "templates"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const create = useMutation({
    mutationFn: async () => (await api.post("/platform/templates", newForm)).data,
    onSuccess: (created) => {
      toast("Template created");
      setCreating(false);
      queryClient.invalidateQueries({ queryKey: ["platform", "templates"] });
      // Straight into the editor: a template you cannot immediately shape is just a
      // copy of something else wearing a new name.
      setEditing(created.key);
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const remove = useMutation({
    mutationFn: async (key: string) => (await api.delete(`/platform/templates/${key}`)).data,
    onSuccess: () => {
      toast("Template deleted");
      setDeleting(null);
      queryClient.invalidateQueries({ queryKey: ["platform", "templates"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const openCreate = () => {
    setNewForm({ key: "", name: "", description: "", base_key: "general_crm" });
    setCreating(true);
  };

  const openClone = (template: CrmTemplate) => {
    setCloning(template);
    setCloneForm({
      key: `${template.key}_copy`,
      name: `${template.name} (copy)`,
      description: template.description ?? "",
    });
  };

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Templates</h1>
          <p className="max-w-2xl text-sm text-slate-500 dark:text-slate-400">
            The recipe a new tenant is built from — which modules they get, what those modules are
            called, plus starting roles, pipeline stages and settings. A template is copied into a
            tenant when it is created, so editing one never changes an existing workspace.
          </p>
        </div>
        <button className="btn-primary shrink-0" onClick={openCreate}>
          <Plus size={16} /> New template
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {templates.data?.map((template) => (
          <div key={template.key} className="card flex flex-col p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="flex items-center gap-2 font-semibold">
                  {template.name}
                  {template.is_system && (
                    <span
                      className="badge bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                      title="Bundled with the product and kept up to date automatically. Clone it to customise."
                    >
                      <Lock size={10} className="mr-1" /> system
                    </span>
                  )}
                </h2>
                <p className="text-xs text-slate-400">{template.key} · v{template.version}</p>
              </div>
            </div>

            <p className="mt-2 flex-1 text-sm text-slate-600 dark:text-slate-300">{template.description}</p>

            <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 text-center dark:border-slate-800">
              {[
                ["Modules", `${template.enabled_module_count}/${template.module_count}`],
                ["Roles", template.role_count],
                ["Stages", template.stage_count],
              ].map(([label, value]) => (
                <div key={label as string}>
                  <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
                  <dd className="text-sm font-medium">{value}</dd>
                </div>
              ))}
            </dl>

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                className={template.is_system ? "btn-secondary flex-1" : "btn-primary flex-1"}
                onClick={() => setEditing(template.key)}
                title={
                  template.is_system
                    ? "System templates are read-only — you will be offered a clone"
                    : "Change which modules a new client gets, and what they are called"
                }
              >
                <Pencil size={14} /> Customise
              </button>
              <button className="btn-secondary shrink-0" onClick={() => setInspecting(template.key)}>
                Inspect
              </button>
              <button className="btn-secondary shrink-0" onClick={() => openClone(template)} title="Clone to customise">
                <Copy size={14} /> Clone
              </button>
              {!template.is_system && (
                <button
                  className="btn-ghost !p-2 text-red-500"
                  title="Delete this custom template"
                  onClick={() => setDeleting(template)}
                >
                  <Trash2 size={15} />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <Modal
        open={!!editing}
        onClose={() => setEditing(null)}
        title={`Customise ${templates.data?.find((t) => t.key === editing)?.name ?? ""}`}
        wide
      >
        {editing && (
          <TemplateEditor
            templateKey={editing}
            onClone={() => {
              const source = templates.data?.find((t) => t.key === editing);
              setEditing(null);
              if (source) openClone(source);
            }}
          />
        )}
      </Modal>

      <Modal open={creating} onClose={() => setCreating(false)} title="New template">
        <div className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            A template starts from an existing one. Starting truly empty would produce a
            workspace with no roles and no pipeline — broken in a way nobody notices until
            its owner tries to sign in. Pick the closest fit, then change what you need.
          </p>
          <div>
            <label className="label">Start from</label>
            <Select
              options={(templates.data ?? []).map((t) => ({ value: t.key, label: t.name }))}
              value={newForm.base_key}
              onChange={(v) => setNewForm({ ...newForm, base_key: v })}
              clearable={false}
            />
          </div>
          <div>
            <label className="label">Name</label>
            <input
              className="input"
              value={newForm.name}
              placeholder="Agency Lite"
              onChange={(e) => {
                const name = e.target.value;
                setNewForm((f) => ({
                  ...f,
                  name,
                  // The key follows the name until it is edited by hand: one field to
                  // fill in for the common case, still overridable for the rest.
                  key: f.key === slugify(f.name) || f.key === "" ? slugify(name) : f.key,
                }));
              }}
              autoFocus
            />
          </div>
          <div>
            <label className="label">Key</label>
            <input
              className="input"
              value={newForm.key}
              placeholder="agency_lite"
              onChange={(e) => setNewForm({ ...newForm, key: e.target.value })}
            />
            <p className="mt-1 text-xs text-slate-400">
              Lowercase letters, numbers and underscores. Permanent — tenants are stamped with it.
            </p>
          </div>
          <div>
            <label className="label">Description</label>
            <textarea
              className="input"
              rows={2}
              placeholder="Who this template is for."
              value={newForm.description}
              onChange={(e) => setNewForm({ ...newForm, description: e.target.value })}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setCreating(false)}>Cancel</button>
            <button
              className="btn-primary"
              disabled={
                create.isPending ||
                newForm.name.trim().length < 2 ||
                !/^[a-z0-9_]{2,}$/.test(newForm.key)
              }
              onClick={() => create.mutate()}
            >
              {create.isPending ? "Creating…" : "Create and customise"}
            </button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting.key)}
        title={`Delete ${deleting?.name ?? ""}?`}
        message="Workspaces already built from it keep everything they were given — a template is copied at provisioning, never referenced afterwards. Only new workspaces lose the option."
        busy={remove.isPending}
      />

      <Modal open={!!cloning} onClose={() => setCloning(null)} title={`Clone ${cloning?.name ?? ""}`}>
        <div className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            System templates are refreshed from the product whenever they change, so edits to them
            would be overwritten. Cloning gives you a copy that is yours to modify.
          </p>
          <div>
            <label className="label">Key</label>
            <input
              className="input"
              value={cloneForm.key}
              onChange={(e) => setCloneForm({ ...cloneForm, key: e.target.value })}
              placeholder="agency_lite"
            />
            <p className="mt-1 text-xs text-slate-400">Lowercase letters, numbers and underscores.</p>
          </div>
          <div>
            <label className="label">Name</label>
            <input
              className="input"
              value={cloneForm.name}
              onChange={(e) => setCloneForm({ ...cloneForm, name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea
              className="input"
              rows={2}
              value={cloneForm.description}
              onChange={(e) => setCloneForm({ ...cloneForm, description: e.target.value })}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setCloning(null)}>Cancel</button>
            <button
              className="btn-primary"
              disabled={clone.isPending || !/^[a-z0-9_]{2,}$/.test(cloneForm.key)}
              onClick={() => clone.mutate()}
            >
              {clone.isPending ? "Cloning…" : "Create clone"}
            </button>
          </div>
        </div>
      </Modal>

      <Modal open={!!inspecting} onClose={() => setInspecting(null)} title={detail.data?.name ?? "Template"} wide>
        {detail.isLoading && <p className="text-slate-400">Loading…</p>}
        {detail.data && (
          <div className="space-y-5">
            <section>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
                Modules
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {(detail.data.config.modules ?? []).map((m: any) => (
                  <span
                    key={m.key}
                    className={clsx(
                      "badge",
                      m.enabled
                        ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                        : "bg-slate-100 text-slate-400 line-through dark:bg-slate-800"
                    )}
                    title={m.key}
                  >
                    {m.label ?? m.key}
                  </span>
                ))}
              </div>
            </section>

            <section>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
                Pipeline stages
              </h3>
              <div className="flex flex-wrap items-center gap-1.5 text-sm">
                {(detail.data.config.stages ?? []).map((s: any, i: number) => (
                  <span key={s.name} className="flex items-center gap-1.5">
                    {i > 0 && <span className="text-slate-300">→</span>}
                    <span className="badge bg-slate-100 dark:bg-slate-800">{s.name}</span>
                  </span>
                ))}
              </div>
            </section>

            <section>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
                Roles
              </h3>
              <ul className="space-y-1 text-sm">
                {(detail.data.config.roles ?? []).map((r: any) => (
                  <li key={r.name}>
                    <span className="font-medium">{r.name}</span>
                    <span className="text-slate-500 dark:text-slate-400"> — {r.description}</span>
                  </li>
                ))}
              </ul>
            </section>

            {detail.data.config.masters && Object.keys(detail.data.config.masters).length > 0 && (
              <section>
                <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
                  Reference data
                </h3>
                <ul className="space-y-1 text-sm">
                  {Object.entries(detail.data.config.masters as Record<string, string[]>).map(([key, values]) => (
                    <li key={key}>
                      <span className="font-medium capitalize">{key.replace(/_/g, " ")}</span>
                      <span className="text-slate-500 dark:text-slate-400"> — {values.length} entries</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
