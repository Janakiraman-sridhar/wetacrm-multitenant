import { zodResolver } from "@hookform/resolvers/zod";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Check, ChevronDown, ChevronRight, LayoutList, ListFilter, Pencil, Plus, Search, Trash2,
} from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z, type ZodTypeAny } from "zod";

import { Column, DataTable } from "@/components/DataTable";
import { DatePicker } from "@/components/DatePicker";
import { FiltersBar } from "@/components/FiltersBar";
import { ImportExport } from "@/components/ImportExport";
import { ConfirmDialog, Modal } from "@/components/Modal";
import { MultiSelect } from "@/components/MultiSelect";
import { Select } from "@/components/Select";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { ActiveFilter, countActive, FilterFieldDef, serializeFilters } from "@/lib/filters";
import { useSchemaOverlay } from "@/lib/schema";
import type { Page } from "@/types";

export interface SelectOption {
  value: string;
  label: string;
}

export interface FieldDef {
  name: string;
  label: string;
  type?: "text" | "email" | "number" | "textarea" | "select" | "multiselect" | "date" | "datetime-local" | "checkbox" | "password";
  options?: SelectOption[];
  placeholder?: string;
  colSpan?: 1 | 2;
  step?: string;
  section?: string; // fields with the same section render under one header
  /**
   * The schema column this field edits, when the form name differs.
   *
   * `phone_primary` and `phone_secondary` both write the `phones` array, and
   * `linkedin`/`twitter` both write `social_links`. Without this the tenant's
   * "hide this field" in Settings → Fields silently reaches neither, because the
   * overlay matches on the form name — so a workspace that captures a Mobile and
   * has no use for a separate Phone could not switch the duplicate off.
   *
   * Hiding only. A relabel stays keyed on the form name, or the two fields sharing
   * a column would both take that column's caption.
   */
  schemaKey?: string;
  /** Rendered full-width below this field, fed the live form values (e.g. a linked-record preview). */
  after?: (values: Record<string, any>) => React.ReactNode;
  /**
   * Take over this row entirely — for a value no `<input>` describes, such as a
   * repeating sub-record. Given the form's `control` so it can register itself with
   * react-hook-form like every other field, which is what keeps validation, dirty
   * state and reset working rather than needing a second state tree beside them.
   */
  render?: (ctx: { control: any; name: string }) => React.ReactNode;
}

// --- form rendering -------------------------------------------------------

function FieldControl({ field: f, register, control, errors }: { field: FieldDef; register: any; control: any; errors: any }) {
  const error = errors?.[f.name];
  return (
    <div className={f.colSpan === 2 ? "sm:col-span-2" : ""}>
      <label className="label" htmlFor={`field-${f.name}`}>
        {f.label}
      </label>
      {f.type === "textarea" ? (
        <textarea id={`field-${f.name}`} rows={3} className="input" placeholder={f.placeholder} {...register(f.name)} />
      ) : f.type === "select" ? (
        <Controller
          name={f.name}
          control={control}
          render={({ field: rhf }) => (
            <Select
              id={`field-${f.name}`}
              value={rhf.value ?? ""}
              onChange={rhf.onChange}
              options={f.options ?? []}
              placeholder={f.placeholder ?? "Select…"}
              error={!!error}
            />
          )}
        />
      ) : f.type === "multiselect" ? (
        <Controller
          name={f.name}
          control={control}
          render={({ field: rhf }) => (
            <MultiSelect
              value={Array.isArray(rhf.value) ? rhf.value : []}
              onChange={rhf.onChange}
              options={f.options ?? []}
              placeholder={f.placeholder ?? "Select…"}
            />
          )}
        />
      ) : f.type === "date" || f.type === "datetime-local" ? (
        <Controller
          name={f.name}
          control={control}
          render={({ field: rhf }) => (
            <DatePicker
              id={`field-${f.name}`}
              value={rhf.value ?? ""}
              onChange={rhf.onChange}
              mode={f.type === "date" ? "date" : "datetime"}
              placeholder={f.placeholder}
              error={!!error}
            />
          )}
        />
      ) : f.type === "checkbox" ? (
        <input id={`field-${f.name}`} type="checkbox" className="h-4 w-4 accent-primary-600" {...register(f.name)} />
      ) : (
        <input
          id={`field-${f.name}`}
          type={f.type ?? "text"}
          step={f.step}
          className={clsx("input", error && "!border-red-400 dark:!border-red-700")}
          placeholder={f.placeholder}
          {...register(f.name, f.type === "number" ? { valueAsNumber: true } : undefined)}
        />
      )}
      {error && <p className="mt-1 text-xs text-red-600">{String(error?.message ?? "Invalid value")}</p>}
    </div>
  );
}

export function FormFields({
  fields,
  register,
  errors,
  control,
  editing = false,
}: {
  fields: FieldDef[];
  register: any;
  errors: any;
  control: any;
  /** Editing an existing record, rather than creating one. */
  editing?: boolean;
}) {
  // Live values for `after` renderers (linked-record previews etc.).
  const values = useWatch({ control }) as Record<string, any>;

  /**
   * One header per section name, in the order each first appears.
   *
   * Grouping only consecutive fields meant a section could be drawn twice: the
   * tenant's own custom fields are appended after the page's, so a workspace with a
   * custom KYC field got two "KYC" headers with the rest of the form between them.
   */
  const groups = useMemo(() => {
    const out: { section?: string; items: FieldDef[] }[] = [];
    const byName = new Map<string, { section?: string; items: FieldDef[] }>();
    for (const f of fields) {
      const existing = f.section ? byName.get(f.section) : undefined;
      if (existing) {
        existing.items.push(f);
        continue;
      }
      const group = { section: f.section, items: [f] };
      // Ungrouped fields keep running into the block above them, as before.
      const last = out[out.length - 1];
      if (!f.section && last && !last.section) last.items.push(f);
      else out.push(group);
      if (f.section) byName.set(f.section, group);
    }
    return out;
  }, [fields]);

  const filled = (f: FieldDef) => {
    const v = values?.[f.name];
    return Array.isArray(v) ? v.length > 0 : v !== undefined && v !== null && v !== "";
  };

  /**
   * Which sections start open.
   *
   * A customer form runs to thirty-three fields over two screens, and an agent with
   * a name and a phone number should not scroll past a KYC block, an address block
   * and a nominee editor to reach Save.
   *
   * Creating opens the first group only — on a new record every other section is
   * empty by definition, and a section that opens because a dropdown has a default
   * is open for no reason. Editing opens whatever has something in it, so nothing a
   * colleague filled in is hidden behind a header nobody thinks to click.
   *
   * Computed once per opening rather than on every keystroke: recomputing would slam
   * a section shut the moment someone cleared the last field they were editing.
   */
  const initiallyOpen = useMemo(
    () =>
      new Set(
        groups
          .filter((g, i) => i === 0 || !g.section || (editing && g.items.some(filled)))
          .map((g) => g.section ?? "")
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [groups.length, editing]
  );
  const [open, setOpen] = useState<Set<string>>(initiallyOpen);
  useEffect(() => setOpen(initiallyOpen), [initiallyOpen]);

  return (
    <div className="space-y-5">
      {groups.map((group, gi) => {
        const key = group.section ?? "";
        const isOpen = !group.section || open.has(key);
        const count = group.items.filter(filled).length;
        return (
        <div key={gi}>
          {group.section && (
            <button
              type="button"
              className="mb-3 flex w-full items-center gap-3 text-left"
              onClick={() =>
                setOpen((prev) => {
                  const next = new Set(prev);
                  next.has(key) ? next.delete(key) : next.add(key);
                  return next;
                })
              }
            >
              <ChevronRight
                size={14}
                className={clsx(
                  "shrink-0 text-slate-400 transition-transform",
                  isOpen && "rotate-90"
                )}
              />
              <span className="text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
                {group.section}
              </span>
              {/* So a collapsed section never hides something silently. */}
              {count > 0 && (
                <span className="badge bg-primary-50 text-[10px] text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">
                  {count}
                </span>
              )}
              {!isOpen && (
                <span className="text-xs text-slate-400">
                  {group.items.length} field{group.items.length === 1 ? "" : "s"}
                </span>
              )}
              <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
            </button>
          )}
          <div className={clsx("grid grid-cols-1 gap-4 sm:grid-cols-2", !isOpen && "hidden")}>
            {group.items.map((f) => (
              <Fragment key={f.name}>
                {f.render ? (
                  <div className="sm:col-span-2">
                    {/* The section header already carries the name when they match,
                        and two identical headings stacked reads as a bug. */}
                    {f.label !== f.section && <label className="label">{f.label}</label>}
                    {f.render({ control, name: f.name })}
                    {/* A custom control skips FieldControl, so its validation message
                        needs showing here or the form refuses to submit in silence. */}
                    {errors?.[f.name] && (
                      <p className="mt-1 text-xs text-red-600">
                        {String(errors[f.name]?.message ?? "Invalid value")}
                      </p>
                    )}
                  </div>
                ) : (
                  <FieldControl field={f} register={register} control={control} errors={errors} />
                )}
                {f.after && <div className="sm:col-span-2">{f.after(values)}</div>}
              </Fragment>
            ))}
          </div>
        </div>
        );
      })}
    </div>
  );
}

// --- saved views ----------------------------------------------------------

interface SavedView {
  name: string;
  columns: string[];
}

/** "default" = curated columns; "all" = every field in the catalog; or a user-saved view. */
export type ViewSelection = "default" | "all" | SavedView;

function loadViews(storageKey: string): SavedView[] {
  try {
    return JSON.parse(localStorage.getItem(storageKey) || "[]");
  } catch {
    return [];
  }
}

function ViewsControl<T extends { id: string }>({
  columns,
  defaultCount,
  storageKey,
  active,
  onActivate,
}: {
  columns: Column<T>[];
  defaultCount: number;
  storageKey: string;
  active: ViewSelection;
  onActivate: (view: ViewSelection) => void;
}) {
  const { toast } = useToast();
  const [views, setViews] = useState<SavedView[]>(() => loadViews(storageKey));
  const [open, setOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingOriginal, setEditingOriginal] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftCols, setDraftCols] = useState<Set<string>>(new Set());
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const persist = (next: SavedView[]) => {
    setViews(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      /* storage unavailable */
    }
  };

  const openEditor = (view?: SavedView) => {
    setEditingOriginal(view?.name ?? null);
    setDraftName(view?.name ?? "");
    setDraftCols(new Set(view ? view.columns : columns.map((c) => c.key)));
    setEditorOpen(true);
    setOpen(false);
  };

  const saveView = () => {
    const name = draftName.trim();
    if (!name) return toast("Give the view a name", "error");
    if (draftCols.size === 0) return toast("Select at least one field", "error");
    if (name !== editingOriginal && views.some((v) => v.name === name)) {
      return toast("A view with this name already exists", "error");
    }
    const view: SavedView = { name, columns: columns.map((c) => c.key).filter((k) => draftCols.has(k)) };
    const next = editingOriginal
      ? views.map((v) => (v.name === editingOriginal ? view : v))
      : [...views, view];
    persist(next);
    setEditorOpen(false);
    onActivate(view);
    toast(editingOriginal ? "View updated" : `View “${name}” created`);
  };

  const deleteView = (name: string) => {
    persist(views.filter((v) => v.name !== name));
    if (typeof active === "object" && active.name === name) onActivate("default");
  };

  const toggleDraftCol = (key: string) => {
    const next = new Set(draftCols);
    next.has(key) ? next.delete(key) : next.add(key);
    setDraftCols(next);
  };

  return (
    <div ref={boxRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="btn-secondary"
        title="Choose which fields are shown in the list"
      >
        <LayoutList size={15} className="text-primary-600 dark:text-primary-400" />
        <span className="max-w-32 truncate">
          {active === "default" ? "Default view" : active === "all" ? "All fields" : active.name}
        </span>
        <ChevronDown size={14} className={clsx("text-slate-400 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="card absolute right-0 top-full z-40 mt-2 w-64 overflow-hidden p-1.5 shadow-xl">
          <p className="px-2.5 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Views</p>
          {(
            [
              { key: "default" as const, label: "Default view", sub: `${defaultCount} key fields` },
              { key: "all" as const, label: "All fields", sub: `every field (${columns.length})` },
            ]
          ).map((builtin) => (
            <button
              key={builtin.key}
              onClick={() => {
                onActivate(builtin.key);
                setOpen(false);
              }}
              className={clsx(
                "flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                active === builtin.key
                  ? "bg-primary-50 font-medium text-primary-700 dark:bg-primary-900/40 dark:text-primary-300"
                  : "hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
            >
              <span>
                <span className="block">{builtin.label}</span>
                <span className="block text-[11px] font-normal text-slate-400">{builtin.sub}</span>
              </span>
              {active === builtin.key && <Check size={14} />}
            </button>
          ))}
          {views.map((view) => (
            <div
              key={view.name}
              className={clsx(
                "group flex w-full items-center gap-1 rounded-lg pr-1 transition-colors",
                typeof active === "object" && active.name === view.name
                  ? "bg-primary-50 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300"
                  : "hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
            >
              <button
                onClick={() => {
                  onActivate(view);
                  setOpen(false);
                }}
                className="min-w-0 flex-1 px-2.5 py-2 text-left text-sm"
              >
                <span className={clsx("block truncate", typeof active === "object" && active.name === view.name && "font-medium")}>{view.name}</span>
                <span className="block text-[11px] text-slate-400">{view.columns.length} fields</span>
              </button>
              {typeof active === "object" && active.name === view.name && <Check size={14} className="shrink-0" />}
              <button
                className="shrink-0 rounded p-1 text-slate-300 opacity-0 transition-opacity hover:text-primary-600 group-hover:opacity-100"
                title="Edit view"
                onClick={() => openEditor(view)}
              >
                <Pencil size={12} />
              </button>
              <button
                className="shrink-0 rounded p-1 text-slate-300 opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100"
                title="Delete view"
                onClick={() => deleteView(view.name)}
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
          <div className="mt-1 border-t border-slate-100 pt-1 dark:border-slate-800">
            <button
              onClick={() => openEditor()}
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-primary-600 hover:bg-primary-50 dark:text-primary-400 dark:hover:bg-primary-900/30"
            >
              <Plus size={14} /> Create view
            </button>
          </div>
        </div>
      )}

      <Modal
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        title={editingOriginal ? `Edit view: ${editingOriginal}` : "Create view"}
      >
        <div className="space-y-4">
          <div>
            <label className="label">View name</label>
            <input
              className="input"
              placeholder="e.g. Sales essentials"
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              autoFocus
            />
          </div>
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="label !mb-0">Fields to show</label>
              <span className="text-xs text-slate-400">
                {draftCols.size} of {columns.length} selected
              </span>
            </div>
            <div className="grid max-h-64 grid-cols-1 gap-1 overflow-y-auto rounded-lg border border-slate-200 p-2 sm:grid-cols-2 dark:border-slate-800">
              {columns.map((col) => (
                <label
                  key={col.key}
                  className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded accent-primary-600"
                    checked={draftCols.has(col.key)}
                    onChange={() => toggleDraftCol(col.key)}
                  />
                  {col.header}
                </label>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-slate-400">Views are saved on this device, per module.</p>
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setEditorOpen(false)}>
              Cancel
            </button>
            <button className="btn-primary" onClick={saveView}>
              {editingOriginal ? "Save changes" : "Create view"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

/**
 * Column-visibility state + the Views button for a module. Used by CrudPage and
 * by custom list pages (Quotations, Invoices) so views behave identically everywhere.
 */
export function useViewColumns<T extends { id: string }>(
  module: string,
  columns: Column<T>[],
  allColumns?: Column<T>[]
) {
  const [active, setActive] = useState<ViewSelection>("default");
  const catalog = allColumns ?? columns;
  const visibleColumns = useMemo(() => {
    if (active === "default") return columns;
    if (active === "all") return catalog;
    return catalog.filter((c) => active.columns.includes(c.key));
  }, [columns, catalog, active]);

  const viewsControl = (
    <ViewsControl
      columns={catalog}
      defaultCount={columns.length}
      storageKey={`weta_views_${module}`}
      active={active}
      onActivate={setActive}
    />
  );
  return { visibleColumns, viewsControl };
}

// --- generic CRUD page ----------------------------------------------------

export interface CrudPageProps<T extends { id: string }> {
  title: string;
  singular?: string; // e.g. "Company"; defaults to title minus trailing "s"
  endpoint: string; // e.g. "/companies"
  module: string; // permission module, e.g. "companies"
  columns: Column<T>[];
  /** Complete field catalog selectable in views; defaults to `columns`. */
  allColumns?: Column<T>[];
  fields: FieldDef[];
  schema: ZodTypeAny;
  defaults: Record<string, any>;
  toForm?: (row: T) => Record<string, any>;
  searchPlaceholder?: string;
  extraParams?: Record<string, string>;
  toolbar?: React.ReactNode;
  /** Enables CSV import/export in the toolbar; the /io registry key (e.g. "companies"). */
  ioEntity?: string;
  /** Enables the date/field filter panel; the filterable fields for this module. */
  filterFields?: FilterFieldDef[];
  rowActions?: (row: T, helpers: { edit: (row: T) => void; remove: (row: T) => void }) => React.ReactNode;
  onRowClick?: (row: T, helpers: { edit: (row: T) => void }) => void;
  createLabel?: string;
}

export function CrudPage<T extends { id: string }>({
  title,
  singular,
  endpoint,
  module,
  columns,
  allColumns,
  fields,
  schema,
  defaults,
  toForm,
  searchPlaceholder = "Search…",
  extraParams,
  toolbar,
  ioEntity,
  filterFields,
  rowActions,
  onRowClick,
  createLabel,
}: CrudPageProps<T>) {
  const { hasPerm } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const one = singular ?? title.replace(/s$/, "");

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<string | null>("-created_at");
  const [filters, setFilters] = useState<ActiveFilter[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<T | null>(null);
  const [deleting, setDeleting] = useState<T | null>(null);

  // What this tenant has done to the module: relabelled or hidden base fields, and
  // fields they added. The page's own arrays stay the base — they carry render
  // details the server cannot know, like which hook supplies a select's options.
  const overlay = useSchemaOverlay(module);

  const relabel = <F extends { label: string }>(key: string, item: F): F =>
    overlay.labels[key] && overlay.labels[key] !== item.label
      ? { ...item, label: overlay.labels[key] }
      : item;

  const effectiveFields = useMemo(
    () => [
      // `schemaKey` decides only whether the field is hidden. Relabelling still
      // keys on the form name: LinkedIn and X both write `social_links`, and
      // applying that column's label to each turned two distinct inputs into two
      // boxes both captioned "Social links".
      ...fields
        .filter((f) => !overlay.hidden.has(f.schemaKey ?? f.name))
        .map((f) => relabel(f.name, f)),
      ...overlay.customFields,
    ],
    [fields, overlay]
  );

  const effectiveColumns = useMemo(
    () => [
      ...columns
        .filter((c) => !overlay.hidden.has(c.key))
        .map((c) => (overlay.labels[c.key] ? { ...c, header: overlay.labels[c.key] } : c)),
      ...(overlay.customColumns as Column<T>[]),
    ],
    [columns, overlay]
  );

  const effectiveAllColumns = useMemo(() => {
    const base = (allColumns ?? columns)
      .filter((c) => !overlay.hidden.has(c.key))
      .map((c) => (overlay.labels[c.key] ? { ...c, header: overlay.labels[c.key] } : c));
    return [...base, ...(overlay.customColumns as Column<T>[])];
  }, [allColumns, columns, overlay]);

  const effectiveFilterFields = useMemo(
    () => [...(filterFields ?? []), ...overlay.customFilters],
    [filterFields, overlay]
  );

  // Custom values submit as { custom: { key: value } }; a plain zod object would
  // strip that key before it reached the API.
  const effectiveSchema = useMemo(() => {
    const anySchema = schema as any;
    if (overlay.customFields.length === 0 || typeof anySchema?.extend !== "function") return schema;
    return anySchema.extend({ custom: z.record(z.any()).optional() });
  }, [schema, overlay.customFields.length]);

  const effectiveDefaults = useMemo(
    () => ({ ...defaults, custom: { ...overlay.defaults } }),
    [defaults, overlay.defaults]
  );

  const { visibleColumns, viewsControl } = useViewColumns(module, effectiveColumns, effectiveAllColumns);

  const filtersParam = useMemo(() => serializeFilters(filters), [filters]);
  const activeFilterCount = countActive(filters);

  const params = useMemo(
    () => ({ page, page_size: pageSize, search: search || undefined, sort: sort || undefined, filters: filtersParam, ...extraParams }),
    [page, pageSize, search, sort, filtersParam, extraParams]
  );

  const query = useQuery({
    queryKey: [endpoint, params],
    queryFn: async () => (await api.get<Page<T>>(endpoint, { params })).data,
    placeholderData: keepPreviousData,
  });

  const form = useForm({ resolver: zodResolver(effectiveSchema as any), defaultValues: effectiveDefaults });

  const openCreate = () => {
    setEditing(null);
    form.reset(effectiveDefaults);
    setModalOpen(true);
  };

  const openEdit = (row: T) => {
    setEditing(row);
    const record = (toForm ? toForm(row) : row) as Record<string, any>;
    form.reset({
      ...effectiveDefaults,
      ...record,
      // Merge rather than replace, so a field added since this record was created
      // still renders with an empty value instead of undefined.
      custom: { ...effectiveDefaults.custom, ...((record.custom as object) ?? {}) },
    });
    setModalOpen(true);
  };

  const saveMutation = useMutation({
    mutationFn: async (values: any) => {
      if (editing) return (await api.patch(`${endpoint}/${editing.id}`, values)).data;
      return (await api.post(endpoint, values)).data;
    },
    onSuccess: () => {
      toast(editing ? `${one} updated` : `${one} created`);
      setModalOpen(false);
      queryClient.invalidateQueries({ queryKey: [endpoint] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: async (row: T) => (await api.delete(`${endpoint}/${row.id}`)).data,
    onSuccess: () => {
      toast(`${one} deleted`);
      setDeleting(null);
      queryClient.invalidateQueries({ queryKey: [endpoint] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const canWrite = hasPerm(`${module}:write`);
  const canDelete = hasPerm(`${module}:delete`);
  const helpers = { edit: openEdit, remove: (row: T) => setDeleting(row) };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{title}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {toolbar}
          {effectiveFilterFields.length > 0 && (
            <button
              className={clsx("btn-secondary", (showFilters || activeFilterCount > 0) && "!border-primary-400 !text-primary-700 dark:!border-primary-600 dark:!text-primary-300")}
              onClick={() => setShowFilters((s) => !s)}
            >
              <ListFilter size={15} /> Filters
              {activeFilterCount > 0 && (
                <span className="ml-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary-600 px-1 text-[10px] font-bold text-white">
                  {activeFilterCount}
                </span>
              )}
            </button>
          )}
          {ioEntity && (
            <ImportExport
              entity={ioEntity}
              module={module}
              label={title}
              filtered={activeFilterCount > 0}
              exportParams={{ filters: filtersParam }}
            />
          )}
          {viewsControl}
          <div className="relative w-full min-w-0 sm:w-auto">
            <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input w-full !pl-8 sm:w-56"
              placeholder={searchPlaceholder}
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          {canWrite && (
            <button className="btn-primary" onClick={openCreate}>
              <Plus size={16} /> {createLabel ?? `New ${one}`}
            </button>
          )}
        </div>
      </div>

      {effectiveFilterFields.length > 0 && (showFilters || activeFilterCount > 0) && (
        <div className="shrink-0">
          <FiltersBar
            fields={effectiveFilterFields}
            value={filters}
            onChange={(f) => {
              setFilters(f);
              setPage(1);
            }}
          />
        </div>
      )}

      <DataTable<T>
        fill
        columns={visibleColumns}
        rows={query.data?.items ?? []}
        total={query.data?.total ?? 0}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(size) => {
          setPageSize(size);
          setPage(1);
        }}
        sort={sort}
        onSortChange={setSort}
        loading={query.isLoading}
        onRowClick={onRowClick ? (row) => onRowClick(row, helpers) : canWrite ? openEdit : undefined}
        actions={(row) => (
          <div className="flex justify-end gap-1">
            {rowActions?.(row, helpers)}
            {canWrite && (
              <button className="btn-ghost !p-1.5" title="Edit" onClick={() => openEdit(row)}>
                <Pencil size={14} />
              </button>
            )}
            {canDelete && (
              <button className="btn-ghost !p-1.5 text-red-500" title="Delete" onClick={() => setDeleting(row)}>
                <Trash2 size={14} />
              </button>
            )}
          </div>
        )}
      />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? `Edit ${one}` : `New ${one}`} wide>
        <form onSubmit={form.handleSubmit((v) => saveMutation.mutate(v))} className="space-y-6">
          <FormFields
            fields={effectiveFields}
            register={form.register}
            errors={form.formState.errors}
            control={form.control}
            editing={!!editing}
          />
          <div className="-mx-5 -mb-5 flex justify-end gap-2 border-t border-slate-200 bg-slate-50/60 px-5 py-3.5 dark:border-slate-800 dark:bg-slate-900/60">
            <button type="button" className="btn-secondary" onClick={() => setModalOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "Saving…" : editing ? "Save changes" : `Create ${one}`}
            </button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && deleteMutation.mutate(deleting)}
        title={`Delete ${one.toLowerCase()}?`}
        message="This action cannot be undone."
        busy={deleteMutation.isPending}
      />
    </div>
  );
}
