import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import clsx from "clsx";
import { useCallback, useEffect, useRef, useState } from "react";

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

// Inset shadows shown on the pinned columns while content is hidden behind them.
const SHADOW_RIGHT = "shadow-[inset_-10px_0_8px_-8px_rgba(15,23,42,0.18)] dark:shadow-[inset_-10px_0_8px_-8px_rgba(0,0,0,0.6)]";
const SHADOW_LEFT = "shadow-[inset_10px_0_8px_-8px_rgba(15,23,42,0.18)] dark:shadow-[inset_10px_0_8px_-8px_rgba(0,0,0,0.6)]";

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
  fill = false,
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
  /** Stretch to fill the parent's height (list pages) instead of growing with content. */
  fill?: boolean;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  const scrollRef = useRef<HTMLDivElement>(null);
  const [hiddenLeft, setHiddenLeft] = useState(false);
  const [hiddenRight, setHiddenRight] = useState(false);

  const updateEdges = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const canScroll = el.scrollWidth > el.clientWidth + 1;
    setHiddenLeft(canScroll && el.scrollLeft > 4);
    setHiddenRight(canScroll && el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
  }, []);

  useEffect(() => {
    updateEdges();
    const el = scrollRef.current;
    if (!el) return;
    el.addEventListener("scroll", updateEdges, { passive: true });
    window.addEventListener("resize", updateEdges);
    return () => {
      el.removeEventListener("scroll", updateEdges);
      window.removeEventListener("resize", updateEdges);
    };
  }, [updateEdges, loading, rows, columns.length]);

  const toggleSort = (key: string) => {
    if (!onSortChange) return;
    if (sort === key) onSortChange(`-${key}`);
    else onSortChange(key);
  };

  if (loading) return <PageSpinner />;

  return (
    <div className={clsx("card flex flex-col overflow-hidden", fill && "min-h-0 flex-1")}>
      <div className={clsx("relative", fill && "min-h-0 flex-1")}>
        <div
          ref={scrollRef}
          className={clsx("overflow-auto", fill ? "h-full" : "max-h-[calc(100vh-280px)]")}
        >
          {/* w-max lets the table grow past the container so wide views scroll
              horizontally; the first and actions columns stay pinned. */}
          <table className="w-max min-w-full border-collapse">
            <thead>
              <tr>
                {columns.map((col, i) => (
                  <th
                    key={col.key}
                    className={clsx(
                      "th",
                      col.sortable && "cursor-pointer select-none hover:text-primary-600",
                      i === 0 && "left-0 z-20 border-r border-slate-200 dark:border-slate-800",
                      i === 0 && hiddenLeft && SHADOW_RIGHT
                    )}
                    onClick={() => col.sortable && toggleSort(col.key)}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.header}
                      {sort === col.key && <ArrowUp size={12} />}
                      {sort === `-${col.key}` && <ArrowDown size={12} />}
                    </span>
                  </th>
                ))}
                {actions && (
                  <th
                    className={clsx(
                      "th sticky right-0 z-20 w-20 border-l border-slate-200 text-right dark:border-slate-800",
                      hiddenRight && SHADOW_LEFT
                    )}
                  >
                    Actions
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className={clsx(
                    "transition-colors odd:bg-white even:bg-slate-50 hover:bg-primary-50 dark:odd:bg-slate-900 dark:even:bg-slate-800 dark:hover:bg-slate-700/80",
                    onRowClick && "cursor-pointer"
                  )}
                  onClick={() => onRowClick?.(row)}
                >
                  {columns.map((col, i) => (
                    <td
                      key={col.key}
                      className={clsx(
                        "td",
                        col.className,
                        i === 0 && "sticky left-0 z-[1] border-r border-slate-100 bg-inherit dark:border-slate-800",
                        i === 0 && hiddenLeft && SHADOW_RIGHT
                      )}
                    >
                      {col.render ? col.render(row) : String((row as any)[col.key] ?? "—") || "—"}
                    </td>
                  ))}
                  {actions && (
                    <td
                      className={clsx(
                        "td sticky right-0 z-[1] border-l border-slate-100 bg-inherit text-right dark:border-slate-800",
                        hiddenRight && SHADOW_LEFT
                      )}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {actions(row)}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <EmptyState title={emptyTitle} subtitle="Create your first record to get started." />}
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-200 px-4 py-2 text-sm text-slate-500 dark:border-slate-800">
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
        {hiddenRight && (
          <span className="hidden items-center gap-1 text-xs text-slate-400 md:flex">
            <ChevronRight size={12} /> scroll right for more fields
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
