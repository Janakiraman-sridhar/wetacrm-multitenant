import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Download, Layers, Search, Table2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { EmptyState, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { downloadCsv } from "@/lib/csv";
import { formatDate, formatMoney } from "@/lib/format";

export interface DrilldownTarget {
  metric: string;
  label: string; // heading shown to the user, e.g. "Total Revenue"
}

type ColumnType = "text" | "badge" | "money" | "number" | "date" | "datetime";

interface DrillColumn {
  key: string;
  label: string;
  type?: ColumnType;
}

interface DrilldownData {
  metric: string;
  title: string;
  start: string;
  end: string;
  columns: DrillColumn[];
  rows: Record<string, any>[];
  total: number;
  truncated: boolean;
}

function formatStamp(value: string, withTime: boolean): string {
  if (!value) return "";
  const d = new Date(value.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return value;
  return withTime
    ? d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function Cell({ column, row }: { column: DrillColumn; row: Record<string, any> }) {
  const value = row[column.key];
  if (value === null || value === undefined || value === "") return <span className="text-slate-300 dark:text-slate-600">—</span>;
  switch (column.type) {
    case "badge":
      return <StatusBadge value={String(value).toLowerCase().replace(/ /g, "_")} />;
    case "money":
      return <span className="font-semibold tabular-nums">{formatMoney(Number(value), row.currency || "INR")}</span>;
    case "number":
      return <span className="tabular-nums">{value}</span>;
    case "date":
      return <span className="whitespace-nowrap text-slate-500 dark:text-slate-400">{formatStamp(String(value), false)}</span>;
    case "datetime":
      return <span className="whitespace-nowrap text-slate-500 dark:text-slate-400">{formatStamp(String(value), true)}</span>;
    default:
      return <span className="font-medium">{String(value)}</span>;
  }
}

function SkeletonRows({ cols }: { cols: number }) {
  return (
    <table className="w-full">
      <tbody>
        {Array.from({ length: 6 }).map((_, r) => (
          <tr key={r}>
            {Array.from({ length: cols }).map((_, c) => (
              <td key={c} className="td">
                <div className="h-3.5 animate-pulse rounded bg-slate-200 dark:bg-slate-800" style={{ width: `${55 + ((r + c) % 4) * 12}%` }} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function DrilldownModal({
  target,
  start,
  end,
  onClose,
}: {
  target: DrilldownTarget | null;
  start: string;
  end: string;
  onClose: () => void;
}) {
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!target) return;
    setSearch("");
    const handler = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [target, onClose]);

  const { data, isLoading } = useQuery({
    queryKey: ["drilldown", target?.metric, start, end],
    queryFn: async () =>
      (await api.get<DrilldownData>("/reports/dashboard/drilldown", {
        params: { metric: target!.metric, start, end },
      })).data,
    enabled: !!target,
  });

  const filteredRows = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    if (!q) return data.rows;
    return data.rows.filter((row) => Object.values(row).some((v) => String(v ?? "").toLowerCase().includes(q)));
  }, [data, search]);

  const moneyColumn = data?.columns.find((c) => c.type === "money");
  const moneyTotal = moneyColumn
    ? filteredRows.reduce((sum, row) => sum + Number(row[moneyColumn.key] || 0), 0)
    : null;

  if (!target) return null;

  const exportCsv = () => {
    if (!data) return;
    downloadCsv(`${target.metric}_${start}_to_${end}.csv`, data.columns, filteredRows);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/60 p-4 backdrop-blur-sm sm:py-10"
      onClick={onClose}
    >
      <div className="card flex max-h-[85vh] w-full max-w-5xl flex-col overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300">
            <Table2 size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-base font-semibold">{target.label}</h2>
            <p className="flex flex-wrap items-center gap-x-2 text-xs text-slate-400">
              <span className="inline-flex items-center gap-1">
                <CalendarDays size={12} />
                {formatDate(start)} – {formatDate(end)}
              </span>
              {data && (
                <>
                  <span aria-hidden>·</span>
                  <span>{data.title}</span>
                </>
              )}
            </p>
          </div>
          <button onClick={onClose} className="btn-ghost order-first !p-1.5 sm:order-none" title="Close (Esc)">
            <X size={16} />
          </button>
        </div>

        {/* Toolbar: summary chips + search + export */}
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50/60 px-5 py-2.5 dark:border-slate-800 dark:bg-slate-900/60">
          <span className="badge gap-1 bg-white text-slate-600 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700">
            <Layers size={11} />
            {data ? `${filteredRows.length}${search ? ` of ${data.total}` : ""} record${(search ? data.total : filteredRows.length) === 1 ? "" : "s"}` : "…"}
          </span>
          {moneyTotal !== null && data && filteredRows.length > 0 && (
            <span className="badge bg-primary-50 font-semibold text-primary-700 ring-1 ring-primary-100 dark:bg-primary-900/40 dark:text-primary-300 dark:ring-primary-900">
              Σ {formatMoney(moneyTotal, filteredRows[0]?.currency || "INR")}
            </span>
          )}
          {data?.truncated && (
            <span className="badge bg-amber-50 text-amber-700 ring-1 ring-amber-100 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-900">
              showing first {data.rows.length}
            </span>
          )}
          <div className="relative ml-auto">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input w-56 !py-1.5 !pl-8 text-sm"
              placeholder="Filter records…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button className="btn-primary !py-1.5" onClick={exportCsv} disabled={!data || filteredRows.length === 0}>
            <Download size={14} /> Export CSV
          </button>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto">
          {isLoading || !data ? (
            <SkeletonRows cols={5} />
          ) : filteredRows.length === 0 ? (
            <EmptyState
              title={search ? "No records match your filter" : "No records in this period"}
              subtitle={search ? "Try a different search term." : "Try a wider date range."}
            />
          ) : (
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr>
                  {data.columns.map((col) => (
                    <th
                      key={col.key}
                      className={`th ${col.type === "money" || col.type === "number" ? "!text-right" : ""}`}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row, i) => (
                  <tr
                    key={i}
                    className="odd:bg-white even:bg-slate-50/60 hover:bg-primary-50/40 dark:odd:bg-slate-900 dark:even:bg-slate-800/30 dark:hover:bg-primary-900/20"
                  >
                    {data.columns.map((col) => (
                      <td
                        key={col.key}
                        className={`td max-w-64 truncate ${col.type === "money" || col.type === "number" ? "text-right" : ""}`}
                        title={String(row[col.key] ?? "")}
                      >
                        <Cell column={col} row={row} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-200 px-5 py-2 text-xs text-slate-400 dark:border-slate-800">
          Click Export CSV to download {search ? "the filtered records" : "everything shown"} for Excel or Sheets.
        </div>
      </div>
    </div>
  );
}
