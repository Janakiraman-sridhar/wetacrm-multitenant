import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import clsx from "clsx";

import { Select } from "./Select";
import { EmptyState, PageSpinner } from "./ui";

export interface Column<T> {
  key: string;
  header: string;
  sortable?: boolean;
  render?: (row: T) => React.ReactNode;
  className?: string;
}

export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100, 200];

export function DataTable<T extends { id: string }>({
  columns,
  rows,
  total,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
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
  onPageSizeChange?: (size: number) => void;
  sort?: string | null;
  onSortChange?: (sort: string) => void;
  loading?: boolean;
  onRowClick?: (row: T) => void;
  actions?: (row: T) => React.ReactNode;
  emptyTitle?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  const toggleSort = (key: string) => {
    if (!onSortChange) return;
    if (sort === key) onSortChange(`-${key}`);
    else onSortChange(key);
  };

  if (loading) return <PageSpinner />;

  return (
    <div className="card overflow-hidden">
      <div className="max-h-[calc(100vh-280px)] overflow-auto">
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
                  "transition-colors odd:bg-white even:bg-slate-50/50 hover:bg-primary-50/40 dark:odd:bg-slate-900 dark:even:bg-slate-800/30 dark:hover:bg-primary-900/20",
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

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-200 px-4 py-2 text-sm text-slate-500 dark:border-slate-800">
        <span className="tabular-nums">
          {total === 0 ? "0 records" : `${from}–${to} of ${total}`}
        </span>
        {onPageSizeChange && (
          <span className="flex items-center gap-2">
            <span className="hidden text-xs sm:inline">Rows per page</span>
            <span className="w-[4.5rem]">
              <Select
                compact
                clearable={false}
                searchable={false}
                direction="up"
                value={String(pageSize)}
                onChange={(v) => onPageSizeChange(Number(v))}
                options={PAGE_SIZE_OPTIONS.map((n) => ({ value: String(n), label: String(n) }))}
              />
            </span>
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <button className="btn-ghost !p-1.5" disabled={page <= 1} onClick={() => onPageChange(1)} title="First page">
            <ChevronsLeft size={15} />
          </button>
          <button className="btn-ghost !p-1.5" disabled={page <= 1} onClick={() => onPageChange(page - 1)} title="Previous page">
            <ChevronLeft size={15} />
          </button>
          <span className="px-1 tabular-nums">
            Page {page} of {pages}
          </span>
          <button className="btn-ghost !p-1.5" disabled={page >= pages} onClick={() => onPageChange(page + 1)} title="Next page">
            <ChevronRight size={15} />
          </button>
          <button className="btn-ghost !p-1.5" disabled={page >= pages} onClick={() => onPageChange(pages)} title="Last page">
            <ChevronsRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
