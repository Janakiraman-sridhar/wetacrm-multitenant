import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Eye, EyeOff, Lock, Plus, Trash2, Wand2 } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog, Modal } from "@/components/Modal";
import { Select } from "@/components/Select";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import type { ModuleSchema, SchemaField } from "@/lib/schema";

const TYPE_LABELS: Record<string, string> = {
  text: "Text", textarea: "Long text", number: "Number", decimal: "Decimal",
  date: "Date", datetime: "Date & time", select: "Dropdown", multiselect: "Multi-select",
  checkbox: "Checkbox", email: "Email", phone: "Phone", url: "Link", currency: "Currency",
};

const NEEDS_OPTIONS = new Set(["select", "multiselect"]);

const blankField = {
  key: "", label: "", field_type: "text", optionsText: "",
  required: false, section: "", help_text: "", placeholder: "",
  show_in_table: false, filterable: false,
};

/**
 * Add, rename, hide and reorder the fields of one module — for this workspace only.
 *
 * Custom fields are stored per tenant, so a field added here is invisible to every
 * other client. Built-in fields can be relabelled and hidden but not deleted, and a
 * few that business logic depends on cannot be hidden at all.
 */
export function FieldEditor({ module, label }: { module: string; label: string }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState(blankField);
  const [deleting, setDeleting] = useState<SchemaField | null>(null);

  const schema = useQuery({
    queryKey: ["schema", module],
    queryFn: async () => (await api.get<ModuleSchema>(`/schema/${module}`)).data,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["schema", module] });
  };

  const createField = useMutation({
    mutationFn: async () => {
      const options = form.optionsText
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => ({ value: line, label: line }));
      return (
        await api.post(`/schema/${module}/fields`, {
          key: form.key.trim().toLowerCase(),
          label: form.label.trim(),
          field_type: form.field_type,
          options,
          required: form.required,
          section: form.section.trim() || null,
          help_text: form.help_text.trim() || null,
          placeholder: form.placeholder.trim() || null,
          show_in_table: form.show_in_table,
          filterable: form.filterable,
        })
      ).data;
    },
    onSuccess: () => {
      toast("Field added");
      setCreateOpen(false);
      setForm(blankField);
      invalidate();
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const patchField = useMutation({
    mutationFn: async ({ key, patch }: { key: string; patch: Record<string, unknown> }) =>
      (await api.patch(`/schema/${module}/fields/${key}`, patch)).data,
    onSuccess: () => invalidate(),
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const removeField = useMutation({
    mutationFn: async (key: string) => (await api.delete(`/schema/${module}/fields/${key}`)).data,
    onSuccess: (data: any) => {
      toast(data?.detail ?? "Field deleted");
      setDeleting(null);
      invalidate();
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const fields = schema.data?.fields ?? [];
  const custom = fields.filter((f) => f.is_custom);
  const builtIn = fields.filter((f) => !f.is_custom);

  const keySuggestion = form.label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40);

  const canCreate =
    form.label.trim().length > 0 &&
    /^[a-z][a-z0-9_]{1,40}$/.test(form.key.trim().toLowerCase() || keySuggestion) &&
    (!NEEDS_OPTIONS.has(form.field_type) || form.optionsText.trim().length > 0);

  const row = (field: SchemaField) => (
    <div key={field.key} className="flex items-center gap-3 py-2.5">
      <input
        className="input !py-1.5 w-52 shrink-0"
        value={field.label}
        onChange={(e) => patchField.mutate({ key: field.key, patch: { label: e.target.value } })}
        aria-label={`Label for ${field.key}`}
      />
      <code className="w-40 shrink-0 truncate text-xs text-slate-400" title={field.key}>
        {field.is_custom ? `custom.${field.key}` : field.key}
      </code>
      <span className="badge shrink-0 bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
        {TYPE_LABELS[field.type] ?? field.type}
      </span>

      <label className="ml-auto flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-slate-500">
        <input
          type="checkbox"
          className="h-3.5 w-3.5 accent-primary-600"
          checked={field.show_in_table}
          onChange={(e) =>
            patchField.mutate({ key: field.key, patch: { show_in_table: e.target.checked } })
          }
        />
        In table
      </label>
      <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-slate-500">
        <input
          type="checkbox"
          className="h-3.5 w-3.5 accent-primary-600"
          checked={field.filterable}
          onChange={(e) =>
            patchField.mutate({ key: field.key, patch: { filterable: e.target.checked } })
          }
        />
        Filter
      </label>

      {field.locked ? (
        <span className="shrink-0 p-1.5 text-slate-300" title="Required by the app — cannot be hidden">
          <Lock size={14} />
        </span>
      ) : (
        <button
          className="btn-ghost shrink-0 !p-1.5"
          title={field.is_active ? "Hide this field" : "Show this field"}
          onClick={() => patchField.mutate({ key: field.key, patch: { is_active: !field.is_active } })}
        >
          {field.is_active ? <Eye size={14} /> : <EyeOff size={14} className="text-slate-400" />}
        </button>
      )}

      {field.is_custom && (
        <button
          className="btn-ghost shrink-0 !p-1.5 text-red-500"
          title="Delete this field"
          onClick={() => setDeleting(field)}
        >
          <Trash2 size={14} />
        </button>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-semibold">{label} fields</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Rename or hide the built-in fields, and add your own. Changes apply to this workspace only.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setCreateOpen(true)}>
          <Plus size={16} /> Add field
        </button>
      </div>

      {custom.length > 0 && (
        <section>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
            Your fields
          </p>
          <div className="card divide-y divide-slate-100 px-4 dark:divide-slate-800">{custom.map(row)}</div>
        </section>
      )}

      <section>
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Built-in fields
        </p>
        <div className="card divide-y divide-slate-100 px-4 dark:divide-slate-800">
          {schema.isLoading && <p className="py-6 text-center text-sm text-slate-400">Loading…</p>}
          {builtIn.map(row)}
        </div>
      </section>

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={`Add a field to ${label}`} wide>
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Label</label>
              <input
                className="input"
                placeholder="e.g. Policy number"
                value={form.label}
                onChange={(e) => setForm({ ...form, label: e.target.value })}
                autoFocus
              />
            </div>
            <div>
              <label className="label">Type</label>
              <Select
                value={form.field_type}
                onChange={(v) => setForm({ ...form, field_type: v })}
                options={Object.entries(TYPE_LABELS).map(([value, l]) => ({ value, label: l }))}
              />
            </div>
            <div className="sm:col-span-2">
              <label className="label">Key</label>
              <div className="flex gap-2">
                <input
                  className="input font-mono text-sm"
                  placeholder={keySuggestion || "policy_number"}
                  value={form.key}
                  onChange={(e) => setForm({ ...form, key: e.target.value })}
                />
                <button
                  className="btn-secondary shrink-0"
                  title="Generate from the label"
                  onClick={() => setForm({ ...form, key: keySuggestion })}
                  disabled={!keySuggestion}
                >
                  <Wand2 size={15} />
                </button>
              </div>
              <p className="mt-1 text-xs text-slate-400">
                Used in exports and filters. Lowercase letters, numbers and underscores; cannot be
                changed later.
              </p>
            </div>

            {NEEDS_OPTIONS.has(form.field_type) && (
              <div className="sm:col-span-2">
                <label className="label">Options</label>
                <textarea
                  className="input"
                  rows={4}
                  placeholder={"Motor\nHealth\nLife"}
                  value={form.optionsText}
                  onChange={(e) => setForm({ ...form, optionsText: e.target.value })}
                />
                <p className="mt-1 text-xs text-slate-400">One per line.</p>
              </div>
            )}

            <div>
              <label className="label">Section</label>
              <input
                className="input"
                placeholder="Additional details"
                value={form.section}
                onChange={(e) => setForm({ ...form, section: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Placeholder</label>
              <input
                className="input"
                value={form.placeholder}
                onChange={(e) => setForm({ ...form, placeholder: e.target.value })}
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-5 border-t border-slate-100 pt-3 dark:border-slate-800">
            {([
              ["required", "Required"],
              ["show_in_table", "Show in table"],
              ["filterable", "Filterable"],
            ] as const).map(([key, text]) => (
              <label key={key} className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-primary-600"
                  checked={form[key] as boolean}
                  onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
                />
                {text}
              </label>
            ))}
          </div>

          <div className="-mx-5 -mb-5 flex justify-end gap-2 border-t border-slate-200 bg-slate-50/60 px-5 py-3.5 dark:border-slate-800 dark:bg-slate-900/60">
            <button className="btn-secondary" onClick={() => setCreateOpen(false)}>Cancel</button>
            <button
              className={clsx("btn-primary")}
              disabled={!canCreate || createField.isPending}
              onClick={() => {
                if (!form.key.trim()) setForm({ ...form, key: keySuggestion });
                createField.mutate();
              }}
            >
              {createField.isPending ? "Adding…" : "Add field"}
            </button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && removeField.mutate(deleting.key)}
        title={`Delete "${deleting?.label}"?`}
        message="The field disappears from forms, tables and exports. Values already saved on records are kept, so recreating the field with the same key brings them back."
        busy={removeField.isPending}
      />
    </div>
  );
}
