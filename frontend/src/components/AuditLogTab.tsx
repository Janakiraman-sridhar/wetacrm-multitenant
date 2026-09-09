import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronDown, ChevronRight, ShieldAlert } from "lucide-react";
import { useState } from "react";

import { Select } from "@/components/Select";
import { Avatar } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

interface AuditRow {
  id: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  changes: Record<string, any>;
  ip_address?: string | null;
  created_at: string;
  user?: { first_name?: string; last_name?: string; full_name?: string } | null;
}

const ACTION_TONES: Record<string, string> = {
  create: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  update: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  delete: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  login: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  reveal: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
};

const label = (p?: { first_name?: string; last_name?: string; full_name?: string } | null) =>
  p?.full_name || [p?.first_name, p?.last_name].filter(Boolean).join(" ") || "System";

/** `{"premium_gross": [12000, 14500]}` reads as "12000 → 14500". */
function Change({ field, value }: { field: string; value: any }) {
  const pair = Array.isArray(value) && value.length === 2;
  const show = (v: any) =>
    v === null || v === undefined || v === "" ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v);
  // A change value can be a whole stored blob, so it wraps and is capped in height
  // rather than running off the card.
  const cell = "max-h-24 overflow-y-auto break-words";
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 py-0.5">
      <span className="shrink-0 font-medium capitalize">{field.replace(/_/g, " ")}</span>
      {pair ? (
        <>
          <span className={clsx(cell, "min-w-0 text-slate-400 line-through")}>{show(value[0])}</span>
          <span className="shrink-0 text-slate-300">→</span>
          <span className={clsx(cell, "min-w-0 text-slate-700 dark:text-slate-200")}>{show(value[1])}</span>
        </>
      ) : (
        <span className={clsx(cell, "min-w-0 text-slate-600 dark:text-slate-300")}>{show(value)}</span>
      )}
    </li>
  );
}

/**
 * Who changed what, and when.
 *
 * Every mutating route has written one of these since the audit helper landed, and
 * nothing has ever read them — the workspace has a complete record of every premium
 * edited and every PAN revealed, and no way to look at it. That is the wrong half of
 * an audit trail to have.
 *
 * Read-only on purpose, and it is not offered as something to delete: a log a user
 * can prune is not evidence of anything.
 */
export function AuditLogTab() {
  const [entityType, setEntityType] = useState("");
  const [page, setPage] = useState(1);
  const [openRow, setOpenRow] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["audit-logs", entityType, page],
    queryFn: async () =>
      (await api.get<{ items: AuditRow[]; total: number; page_size: number }>("/audit-logs", {
        params: { page, page_size: 25, ...(entityType ? { entity_type: entityType } : {}) },
      })).data,
  });

  const rows = data?.items ?? [];
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  // Built from what is actually in the log rather than a hardcoded list, so a
  // record type added later shows up here without anyone remembering to add it.
  const types = Array.from(new Set(rows.map((r) => r.entity_type))).sort();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm text-slate-500 dark:text-slate-400">
          Every create, change and deletion in this workspace, with the old and new values
          and who made it. Written automatically and not editable from here — a log
          somebody can tidy is not worth keeping.
        </p>
        <div className="w-48">
          <Select
            options={types.map((t) => ({ value: t, label: t.replace(/_/g, " ") }))}
            value={entityType}
            onChange={(v) => { setEntityType(v); setPage(1); }}
            placeholder="All record types"
          />
        </div>
      </div>

      <div className="card divide-y divide-slate-100 dark:divide-slate-800">
        {isLoading && <p className="p-6 text-center text-sm text-slate-400">Loading…</p>}

        {!isLoading && rows.length === 0 && (
          <div className="flex flex-col items-center gap-2 p-10 text-center">
            <ShieldAlert size={22} className="text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Nothing recorded yet{entityType ? ` for ${entityType}` : ""}.
            </p>
          </div>
        )}

        {rows.map((row) => {
          const fields = Object.entries(row.changes ?? {});
          const expandable = fields.length > 0;
          const isOpen = openRow === row.id;
          return (
            <div key={row.id}>
              <button
                className={clsx(
                  "flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors",
                  expandable && "hover:bg-slate-50 dark:hover:bg-slate-800/40"
                )}
                onClick={() => expandable && setOpenRow(isOpen ? null : row.id)}
              >
                <span className="w-4 shrink-0 text-slate-300">
                  {expandable ? (isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : null}
                </span>
                <span
                  className={clsx(
                    "badge shrink-0",
                    ACTION_TONES[row.action] ?? ACTION_TONES.login
                  )}
                >
                  {row.action}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm capitalize">
                    {row.entity_type.replace(/_/g, " ")}
                    {fields.length > 0 && (
                      <span className="text-slate-400">
                        {" · "}
                        {fields.length} field{fields.length === 1 ? "" : "s"}
                      </span>
                    )}
                  </span>
                  <span className="block truncate text-xs text-slate-400">
                    {formatDateTime(row.created_at)}
                    {row.ip_address ? ` · ${row.ip_address}` : ""}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1.5">
                  <Avatar first={row.user?.first_name ?? "S"} last={row.user?.last_name ?? ""} size={22} />
                  <span className="hidden max-w-[9rem] truncate text-xs text-slate-500 sm:inline dark:text-slate-400">
                    {label(row.user)}
                  </span>
                </span>
              </button>

              {isOpen && (
                <ul className="border-t border-slate-100 bg-slate-50/60 px-4 py-2.5 text-xs dark:border-slate-800 dark:bg-slate-800/30">
                  {fields.map(([field, value]) => (
                    <Change key={field} field={field} value={value} />
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">
            Page {page} of {pages} · {data?.total} entries
          </span>
          <div className="flex gap-2">
            <button className="btn-secondary !py-1.5" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <button className="btn-secondary !py-1.5" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
