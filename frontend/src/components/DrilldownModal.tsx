import { useQuery } from "@tanstack/react-query";
import { Download, X } from "lucide-react";
import { useEffect } from "react";

import { EmptyState, PageSpinner } from "@/components/ui";
import { api } from "@/lib/api";
import { CsvColumn, downloadCsv } from "@/lib/csv";

export interface DrilldownTarget {
  metric: string;
  label: string; // heading shown to the user, e.g. "Total Revenue"
}

interface DrilldownData {
  metric: string;
  title: string;
  start: string;
  end: string;
  columns: CsvColumn[];
  rows: Record<string, unknown>[];
  total: number;
  truncated: boolean;
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
  useEffect(() => {
    if (!target) return;
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

  if (!target) return null;

  const exportCsv = () => {
    if (!data) return;
    downloadCsv(`${target.metric}_${start}_to_${end}.csv`, data.columns, data.rows);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 backdrop-blur-sm sm:py-10"
      onClick={onClose}
    >
      <div className="card flex max-h-[85vh] w-full max-w-5xl flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-3.5 dark:border-slate-800">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold">{target.label}</h2>
            <p className="text-xs text-slate-400">
              {data ? `${data.title} · ` : ""}
              {start} → {end}
              {data ? ` · ${data.total} record${data.total === 1 ? "" : "s"}` : ""}
              {data?.truncated ? ` (showing first ${data.rows.length})` : ""}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button className="btn-secondary" onClick={exportCsv} disabled={!data || data.rows.length === 0}>
              <Download size={15} /> Export CSV
            </button>
            <button onClick={onClose} className="btn-ghost !p-1.5">
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto">
          {isLoading || !data ? (
            <PageSpinner />
          ) : data.rows.length === 0 ? (
            <EmptyState title="No records in this period" subtitle="Try a wider date range." />
          ) : (
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr>
                  {data.columns.map((col) => (
                    <th key={col.key} className="th">
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, i) => (
                  <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    {data.columns.map((col) => (
                      <td key={col.key} className="td max-w-64 truncate" title={String(row[col.key] ?? "")}>
                        {String(row[col.key] ?? "") || "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
