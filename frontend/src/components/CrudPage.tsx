import { zodResolver } from "@hookform/resolvers/zod";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, ChevronDown, LayoutList, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import type { ZodTypeAny } from "zod";

import { Column, DataTable } from "@/components/DataTable";
import { DatePicker } from "@/components/DatePicker";
import { ImportExport } from "@/components/ImportExport";
import { ConfirmDialog, Modal } from "@/components/Modal";
import { Select } from "@/components/Select";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import type { Page } from "@/types";

export interface SelectOption {
  value: string;
  label: string;
}

export interface FieldDef {
  name: string;
  label: string;
  type?: "text" | "email" | "number" | "textarea" | "select" | "date" | "datetime-local" | "checkbox" | "password";
  options?: SelectOption[];
  placeholder?: string;
  colSpan?: 1 | 2;
  step?: string;
  section?: string; // fields with the same section render under one header
  /** Rendered full-width below this field, fed the live form values (e.g. a linked-record preview). */
  after?: (values: Record<string, any>) => React.ReactNode;
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
}: {
  fields: FieldDef[];
  register: any;
  errors: any;
  control: any;
}) {
  // Live values for `after` renderers (linked-record previews etc.).
  const values = useWatch({ control }) as Record<string, any>;

  // Group consecutive fields that share a section under one header.
  const groups = useMemo(() => {
    const out: { section?: string; items: FieldDef[] }[] = [];
    for (const f of fields) {
      const last = out[out.length - 1];
      if (last && last.section === f.section) last.items.push(f);
      else out.push({ section: f.section, items: [f] });
    }
    return out;
  }, [fields]);

  return (
    <div className="space-y-5">
      {groups.map((group, gi) => (
        <div key={gi}>
          {group.section && (
            <div className="mb-3 flex items-center gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
                {group.section}
              </span>
              <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {group.items.map((f) => (
              <Fragment key={f.name}>
                <FieldControl field={f} register={register} control={control} errors={errors} />
                {f.after && <div className="sm:col-span-2">{f.after(values)}</div>}
              </Fragment>
            ))}
          </div>
        </div>
      ))}
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
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<T | null>(null);
  const [deleting, setDeleting] = useState<T | null>(null);
  const { visibleColumns, viewsControl } = useViewColumns(module, columns, allColumns);

  const params = useMemo(
    () => ({ page, page_size: pageSize, search: search || undefined, sort: sort || undefined, ...extraParams }),
    [page, pageSize, search, sort, extraParams]
  );

  const query = useQuery({
    queryKey: [endpoint, params],
    queryFn: async () => (await api.get<Page<T>>(endpoint, { params })).data,
    placeholderData: keepPreviousData,
  });

  const form = useForm({ resolver: zodResolver(schema as any), defaultValues: defaults });

  const openCreate = () => {
    setEditing(null);
    form.reset(defaults);
    setModalOpen(true);
  };

  const openEdit = (row: T) => {
    setEditing(row);
    form.reset({ ...defaults, ...(toForm ? toForm(row) : row) });
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
          {ioEntity && <ImportExport entity={ioEntity} module={module} label={title} />}
          {viewsControl}
          <div className="relative">
            <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input w-56 !pl-8"
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
          <FormFields fields={fields} register={form.register} errors={form.formState.errors} control={form.control} />
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
