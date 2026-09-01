import { zodResolver } from "@hookform/resolvers/zod";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import type { ZodTypeAny } from "zod";

import { Column, DataTable } from "@/components/DataTable";
import { ConfirmDialog, Modal } from "@/components/Modal";
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
}

export function FormFields({ fields, register, errors }: { fields: FieldDef[]; register: any; errors: any }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {fields.map((f) => (
        <div key={f.name} className={f.colSpan === 2 ? "sm:col-span-2" : ""}>
          <label className="label" htmlFor={`field-${f.name}`}>
            {f.label}
          </label>
          {f.type === "textarea" ? (
            <textarea id={`field-${f.name}`} rows={3} className="input" placeholder={f.placeholder} {...register(f.name)} />
          ) : f.type === "select" ? (
            <select id={`field-${f.name}`} className="input" {...register(f.name)}>
              <option value="">—</option>
              {(f.options ?? []).map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          ) : f.type === "checkbox" ? (
            <input id={`field-${f.name}`} type="checkbox" className="h-4 w-4 accent-primary-600" {...register(f.name)} />
          ) : (
            <input
              id={`field-${f.name}`}
              type={f.type ?? "text"}
              step={f.step}
              className="input"
              placeholder={f.placeholder}
              {...register(f.name, f.type === "number" ? { valueAsNumber: true } : undefined)}
            />
          )}
          {errors?.[f.name] && (
            <p className="mt-1 text-xs text-red-600">{String(errors[f.name]?.message ?? "Invalid value")}</p>
          )}
        </div>
      ))}
    </div>
  );
}

export interface CrudPageProps<T extends { id: string }> {
  title: string;
  singular?: string; // e.g. "Company"; defaults to title minus trailing "s"
  endpoint: string; // e.g. "/companies"
  module: string; // permission module, e.g. "companies"
  columns: Column<T>[];
  fields: FieldDef[];
  schema: ZodTypeAny;
  defaults: Record<string, any>;
  toForm?: (row: T) => Record<string, any>;
  searchPlaceholder?: string;
  extraParams?: Record<string, string>;
  toolbar?: React.ReactNode;
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
  fields,
  schema,
  defaults,
  toForm,
  searchPlaceholder = "Search…",
  extraParams,
  toolbar,
  rowActions,
  onRowClick,
  createLabel,
}: CrudPageProps<T>) {
  const { hasPerm } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const one = singular ?? title.replace(/s$/, "");

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<string | null>("-created_at");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<T | null>(null);
  const [deleting, setDeleting] = useState<T | null>(null);

  const params = useMemo(
    () => ({ page, page_size: 20, search: search || undefined, sort: sort || undefined, ...extraParams }),
    [page, search, sort, extraParams]
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
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{title}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {toolbar}
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
        columns={columns}
        rows={query.data?.items ?? []}
        total={query.data?.total ?? 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
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
        <form onSubmit={form.handleSubmit((v) => saveMutation.mutate(v))} className="space-y-5">
          <FormFields fields={fields} register={form.register} errors={form.formState.errors} />
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setModalOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "Saving…" : "Save"}
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
