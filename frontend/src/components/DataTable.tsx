import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import clsx from "clsx";

import { EmptyState, PageSpinner } from "./ui";

export interface Column<T> {
  key: string;
  header: string;
  sortable?: boolean;
  render?: (row: T) => React.ReactNode;
  className?: string;
}

export function DataTable<T extends { id: string }>({
  columns,
  rows,
  total,
  page,
  pageSize,
  onPageChange,
  sort,
  onSortChange,
  loading,
  onRowClick,
  actions,
  emptyTitle = "Nothing here yet",
}: {
  columns: Column<T>[];
  rows: T[];
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  sort?: string | null;
  onSortChange?: (sort: string) => void;
  loading?: boolean;
  onRowClick?: (row: T) => void;
  actions?: (row: T) => React.ReactNode;
  emptyTitle?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));

  const toggleSort = (key: string) => {
    if (!onSortChange) return;
    if (sort === key) onSortChange(`-${key}`);
    else onSortChange(key);
  };

  if (loading) return <PageSpinner />;

  return (
    <div className="card overflow-hidden">
      <div className="max-h-[calc(100vh-260px)] overflow-auto">
        <table className="w-full min-w-[640px] border-collapse">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={clsx("th", col.sortable && "cursor-pointer select-none hover:text-primary-600")}
                  onClick={() => col.sortable && toggleSort(col.key)}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.header}
                    {sort === col.key && <ArrowUp size={12} />}
                    {sort === `-${col.key}` && <ArrowDown size={12} />}
                  </span>
                </th>
              ))}
              {actions && <th className="th w-20 text-right">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                className={clsx(
                  "transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50",
                  onRowClick && "cursor-pointer"
                )}
                onClick={() => onRowClick?.(row)}
              >
                {columns.map((col) => (
                  <td key={col.key} className={clsx("td", col.className)}>
                    {col.render ? col.render(row) : String((row as any)[col.key] ?? "—")}
                  </td>
                ))}
                {actions && (
                  <td className="td text-right" onClick={(e) => e.stopPropagation()}>
                    {actions(row)}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <EmptyState title={emptyTitle} subtitle="Create your first record to get started." />}
      </div>
      <div className="flex items-center justify-between border-t border-slate-200 px-4 py-2.5 text-sm text-slate-500 dark:border-slate-800">
        <span>
          {total} record{total === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-2">
          <button className="btn-ghost !p-1.5" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
            <ChevronLeft size={16} />
          </button>
          <span>
            Page {page} of {pages}
          </span>
          <button className="btn-ghost !p-1.5" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
