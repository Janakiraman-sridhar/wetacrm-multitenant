import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, Plus, RotateCcw, Trash2, X } from "lucide-react";
import { useState } from "react";

import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import type { Master } from "@/types";

/**
 * The lists this workspace's dropdowns are built from.
 *
 * These were seeded once from the template and there was no way to change them
 * afterwards, so an agency that started writing with an insurer the template did
 * not list had no way to record it — the only route in was the API. A dropdown a
 * workspace cannot maintain is a dropdown that goes stale the first time the market
 * moves.
 */
const LISTS = [
  {
    type: "insurer",
    label: "Insurers",
    hint: "Who underwrites the risk — the company whose name is on the policy.",
  },
  {
    type: "broker",
    label: "Insurance companies",
    hint: "Intermediaries you place business through. Kept apart from insurers because commission is reconciled against both.",
  },
  { type: "bank", label: "Banks", hint: "Bancassurance partners, and lenders for loan cases." },
  { type: "branch", label: "Branches", hint: "Your own offices, for attributing business." },
  { type: "product_type", label: "Product types", hint: "The products you write." },
  { type: "loan_type", label: "Loan types", hint: "The loan products you place." },
  { type: "relation", label: "Relations", hint: "Nominee and family relations." },
] as const;

function ListEditor({ type, label, hint, canWrite }: {
  type: string; label: string; hint: string; canWrite: boolean;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState("");
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["masters", type],
    queryFn: async () => (await api.get<Master[]>("/masters", { params: { type } })).data,
  });

  const done = (message: string) => {
    toast(message);
    // Every dropdown reading this list, on every page, refreshes with it.
    queryClient.invalidateQueries({ queryKey: ["masters", type] });
  };

  const create = useMutation({
    mutationFn: async (name: string) => (await api.post("/masters", { type, name })).data,
    onSuccess: () => { setAdding(""); done(`Added to ${label.toLowerCase()}`); },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const rename = useMutation({
    mutationFn: async ({ id, name }: { id: string; name: string }) =>
      (await api.patch(`/masters/${id}`, { name })).data,
    onSuccess: () => { setEditing(null); done("Renamed"); },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const setActive = useMutation({
    mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) =>
      (await api.patch(`/masters/${id}`, { is_active })).data,
    onSuccess: (_d, v) => done(v.is_active ? "Back in the list" : "Retired"),
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/masters/${id}`)).data,
    // The API deactivates one that is in use rather than deleting it, so historical
    // records keep the name they were actually written with. Its message says which
    // happened, so it is shown rather than replaced with a guess.
    onSuccess: (result: { detail?: string }) => done(result?.detail ?? "Removed"),
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const rows = data ?? [];
  const live = rows.filter((m) => m.is_active);
  const retired = rows.filter((m) => !m.is_active);

  return (
    <section className="card p-5">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">{label}</h3>
        <span className="text-xs text-slate-400">{live.length} in use</span>
      </div>
      <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">{hint}</p>

      {isLoading ? (
        <p className="py-4 text-sm text-slate-400">Loading…</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {live.map((row) =>
            editing?.id === row.id ? (
              <span key={row.id} className="flex items-center gap-1">
                <input
                  className="input !w-40 !py-1 text-sm"
                  value={editing.name}
                  autoFocus
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && editing.name.trim()) rename.mutate(editing);
                    if (e.key === "Escape") setEditing(null);
                  }}
                />
                <button
                  className="btn-ghost !p-1 text-emerald-600"
                  title="Save"
                  disabled={!editing.name.trim()}
                  onClick={() => rename.mutate(editing)}
                >
                  <Check size={14} />
                </button>
                <button className="btn-ghost !p-1 text-slate-400" title="Cancel" onClick={() => setEditing(null)}>
                  <X size={14} />
                </button>
              </span>
            ) : (
              <span
                key={row.id}
                className="badge gap-1 bg-slate-100 py-1 pl-2.5 pr-1 text-slate-700 dark:bg-slate-800 dark:text-slate-200"
              >
                <button
                  className={clsx("truncate", canWrite && "hover:text-primary-600 dark:hover:text-primary-400")}
                  title={canWrite ? "Rename" : undefined}
                  disabled={!canWrite}
                  onClick={() => setEditing({ id: row.id, name: row.name })}
                >
                  {row.name}
                </button>
                {canWrite && (
                  <button
                    className="rounded-full p-0.5 text-slate-400 transition-colors hover:bg-slate-200 hover:text-red-500 dark:hover:bg-slate-700"
                    title={`Remove ${row.name}`}
                    onClick={() => remove.mutate(row.id)}
                  >
                    <Trash2 size={11} />
                  </button>
                )}
              </span>
            )
          )}
          {live.length === 0 && (
            <span className="text-sm text-slate-400">Nothing here yet.</span>
          )}
        </div>
      )}

      {canWrite && (
        <div className="mt-3 flex gap-2">
          <input
            className="input !py-1.5"
            placeholder={`Add to ${label.toLowerCase()}…`}
            value={adding}
            onChange={(e) => setAdding(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && adding.trim() && create.mutate(adding.trim())}
          />
          <button
            className="btn-secondary shrink-0"
            disabled={!adding.trim() || create.isPending}
            onClick={() => create.mutate(adding.trim())}
          >
            <Plus size={14} /> Add
          </button>
        </div>
      )}

      {/* Retired entries stay visible: a policy still names them, and someone will
          want to know why an insurer vanished from the dropdown. */}
      {retired.length > 0 && (
        <div className="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Retired · still named by existing records
          </p>
          <div className="flex flex-wrap gap-1.5">
            {retired.map((row) => (
              <span
                key={row.id}
                className="badge gap-1 bg-slate-50 py-1 pl-2.5 pr-1 text-slate-400 line-through dark:bg-slate-900"
              >
                {row.name}
                {canWrite && (
                  <button
                    className="rounded-full p-0.5 text-slate-400 no-underline transition-colors hover:text-primary-600"
                    title={`Put ${row.name} back in the list`}
                    onClick={() => setActive.mutate({ id: row.id, is_active: true })}
                  >
                    <RotateCcw size={11} />
                  </button>
                )}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export function MastersTab({ canWrite }: { canWrite: boolean }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500 dark:text-slate-400">
        The lists behind the dropdowns on policies, loans and quotations. A workspace
        starts with what its template seeded and maintains them from here.
      </p>
      <div className="grid gap-4 xl:grid-cols-2">
        {LISTS.map((list) => (
          <ListEditor key={list.type} {...list} canWrite={canWrite} />
        ))}
      </div>
    </div>
  );
}
