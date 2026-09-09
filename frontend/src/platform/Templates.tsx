import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Building2, Copy, Layers, Lock, Pencil, Plus, Trash2, Workflow } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ConfirmDialog, Modal } from "@/components/Modal";
import { Select } from "@/components/Select";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { moduleIcon } from "@/lib/modules";
import { CatalogModule, mergeWithCatalog } from "@/platform/ModuleBoard";
import type { CrmTemplate, CrmTemplateDetail } from "@/types";

/** "Agency Lite" becomes "agency_lite" — mirrors the key pattern the API enforces. */
function slugify(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

/**
 * One template, showing what a client built from it actually gets.
 *
 * The counts alone ("15/18 modules") say nothing an admin can act on. The modules
 * themselves, named the way that client will see them, answer the only question the
 * card is really being asked: *is this the right starting point for the customer in
 * front of me?*
 */
function TemplateCard({
  template,
  catalog,
  onEdit,
  onClone,
  onDelete,
}: {
  template: CrmTemplate;
  catalog: CatalogModule[] | undefined;
  onEdit: () => void;
  onClone: () => void;
  onDelete: () => void;
}) {
  const { data: detail } = useQuery({
    queryKey: ["platform", "template", template.key],
    queryFn: async () =>
      (await api.get<CrmTemplateDetail>(`/platform/templates/${template.key}`)).data,
    staleTime: 60_000,
  });

  const included = catalog && detail
    ? mergeWithCatalog(catalog, detail.config.modules).filter((m) => m.enabled)
    : [];
  const stages: { name: string }[] = detail?.config.stages ?? [];

  return (
    <article className="card flex flex-col p-5 transition-shadow hover:shadow-md">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 font-semibold">
            <span className="truncate">{template.name}</span>
            {template.is_system && (
              <span
                className="badge shrink-0 bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                title="Ships with the product and is kept up to date automatically. Clone it to customise."
              >
                <Lock size={10} className="mr-1" /> system
              </span>
            )}
          </h2>
          <p className="truncate font-mono text-xs text-slate-400">
            {template.key} · v{template.version}
          </p>
        </div>
      </header>

      <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{template.description}</p>

      <div className="mt-4 space-y-3 border-t border-slate-100 pt-3 dark:border-slate-800">
        <div>
          {/* Counted against the whole catalog, not against the handful the stored
              config happens to name — "5 of 7" reads as though 7 were on offer. */}
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            They get {included.length} of {catalog?.length ?? template.module_count} modules
          </p>
          <div className="flex flex-wrap gap-1">
            {included.slice(0, 9).map((m) => {
              const Icon = moduleIcon(catalog?.find((c) => c.key === m.key)?.icon ?? "Circle");
              return (
                <span
                  key={m.key}
                  className="badge gap-1 bg-slate-100 py-1 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                  title={m.key}
                >
                  <Icon size={11} /> {m.label}
                </span>
              );
            })}
            {included.length > 9 && (
              <span className="badge bg-slate-100 py-1 text-slate-400 dark:bg-slate-800">
                +{included.length - 9}
              </span>
            )}
            {included.length === 0 && (
              <span className="text-sm text-slate-400">Loading…</span>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1.5">
            <Workflow size={12} className="text-slate-400" />
            {stages.length
              ? stages.slice(0, 3).map((s) => s.name).join(" → ") +
                (stages.length > 3 ? ` → +${stages.length - 3}` : "")
              : `${template.stage_count} stages`}
          </span>
          <span className="flex items-center gap-1.5">
            <Layers size={12} className="text-slate-400" />
            {template.role_count} roles
          </span>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          className={clsx("flex-1", template.is_system ? "btn-secondary" : "btn-primary")}
          onClick={onEdit}
          title={
            template.is_system
              ? "Look inside — system templates are read-only, and you will be offered a clone"
              : "Change which modules a new client gets, and what they are called"
          }
        >
          <Pencil size={14} /> {template.is_system ? "View setup" : "Customise"}
        </button>
        <button className="btn-secondary shrink-0" onClick={onClone} title="Make a copy you can change">
          <Copy size={14} /> Clone
        </button>
        {!template.is_system && (
          <button
            className="btn-ghost !p-2 text-red-500"
            title="Delete this custom template"
            onClick={onDelete}
          >
            <Trash2 size={15} />
          </button>
        )}
      </div>
    </article>
  );
}

export default function Templates() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [cloning, setCloning] = useState<CrmTemplate | null>(null);
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
  const { data: catalog } = useQuery({
    queryKey: ["platform", "module-catalog"],
    queryFn: async () => (await api.get<CatalogModule[]>("/platform/module-catalog")).data,
    staleTime: 10 * 60_000,
  });

  const openClone = (template: CrmTemplate) => {
    setCloning(template);
    setCloneForm({
      key: `${template.key}_copy`,
      name: `${template.name} (copy)`,
      description: template.description ?? "",
    });
  };

  // The read-only editor sends people here to clone; pick that up so the button
  // lands on the filled-in dialog rather than on a page they have to re-navigate.
  useEffect(() => {
    const wanted = params.get("clone");
    if (!wanted || !templates.data) return;
    const found = templates.data.find((t) => t.key === wanted);
    if (found) openClone(found);
    setParams({}, { replace: true });
  }, [params, templates.data, setParams]);

  const clone = useMutation({
    mutationFn: async () =>
      (await api.post(`/platform/templates/${cloning!.key}/clone`, cloneForm)).data,
    onSuccess: (created: CrmTemplate) => {
      toast("Template cloned");
      setCloning(null);
      queryClient.invalidateQueries({ queryKey: ["platform", "templates"] });
      navigate(`/platform/templates/${created.key}`);
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const create = useMutation({
    mutationFn: async () => (await api.post("/platform/templates", newForm)).data,
    onSuccess: (created: CrmTemplate) => {
      toast("Template created");
      setCreating(false);
      queryClient.invalidateQueries({ queryKey: ["platform", "templates"] });
      // Straight into the editor: a template you cannot immediately shape is just a
      // copy of something else wearing a new name.
      navigate(`/platform/templates/${created.key}`);
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

  const all = templates.data ?? [];
  const custom = all.filter((t) => !t.is_system);
  const system = all.filter((t) => t.is_system);

  const grid = (rows: CrmTemplate[]) => (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {rows.map((template) => (
        <TemplateCard
          key={template.key}
          template={template}
          catalog={catalog}
          onEdit={() => navigate(`/platform/templates/${template.key}`)}
          onClone={() => openClone(template)}
          onDelete={() => setDeleting(template)}
        />
      ))}
    </div>
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Templates</h1>
          <p className="max-w-2xl text-sm text-slate-500 dark:text-slate-400">
            The starting point a new client workspace is built from — which modules they get,
            what those modules are called, and the pipeline, roles and lists they begin with.
            A template is <strong>copied</strong> into a workspace when it is created, so
            editing one never changes a client who already exists.
          </p>
        </div>
        <button className="btn-primary shrink-0" onClick={() => {
          setNewForm({ key: "", name: "", description: "", base_key: "general_crm" });
          setCreating(true);
        }}>
          <Plus size={16} /> New template
        </button>
      </div>

      {/* Yours first: the system ones are reference material, the custom ones are the
          work. The old page mixed them and buried a custom template among copies. */}
      <section className="space-y-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Your templates
        </h2>
        {custom.length ? grid(custom) : (
          <div className="card flex flex-col items-center gap-2 p-8 text-center">
            <Building2 size={24} className="text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-slate-500 dark:text-slate-400">
              None yet. Clone the one closest to your client and change what differs — that is
              faster, and safer, than starting from nothing.
            </p>
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Built in
        </h2>
        {grid(system)}
      </section>

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
              options={all.map((t) => ({ value: t.key, label: t.name }))}
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
              className="input font-mono"
              value={newForm.key}
              placeholder="agency_lite"
              onChange={(e) => setNewForm({ ...newForm, key: e.target.value })}
            />
            <p className="mt-1 text-xs text-slate-400">
              Lowercase letters, numbers and underscores. Permanent — workspaces are stamped with it.
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
            You get a copy that is yours to change, opened for editing straight away. The
            original is untouched, and so is every workspace already built from it.
          </p>
          <div>
            <label className="label">Name</label>
            <input
              className="input"
              value={cloneForm.name}
              autoFocus
              onChange={(e) => {
                const name = e.target.value;
                setCloneForm((f) => ({
                  ...f,
                  name,
                  key: f.key === slugify(f.name) || f.key === "" ? slugify(name) : f.key,
                }));
              }}
            />
          </div>
          <div>
            <label className="label">Key</label>
            <input
              className="input font-mono"
              value={cloneForm.key}
              onChange={(e) => setCloneForm({ ...cloneForm, key: e.target.value })}
              placeholder="agency_lite"
            />
            <p className="mt-1 text-xs text-slate-400">Lowercase letters, numbers and underscores.</p>
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
              {clone.isPending ? "Cloning…" : "Clone and customise"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
