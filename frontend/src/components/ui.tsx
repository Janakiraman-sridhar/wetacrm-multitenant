import clsx from "clsx";
import { Loader2 } from "lucide-react";

import { initials } from "@/lib/format";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("animate-spin text-primary-600", className)} size={20} />;
}

export function PageSpinner() {
  return (
    <div className="flex h-64 items-center justify-center">
      <Spinner className="h-8 w-8" />
    </div>
  );
}

const badgePalette: Record<string, string> = {
  // statuses
  new: "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300",
  contacted: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300",
  qualified: "bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300",
  unqualified: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  converted: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
  open: "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300",
  won: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
  lost: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
  todo: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  in_progress: "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
  done: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
  cancelled: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
  draft: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  sent: "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300",
  accepted: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
  declined: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
  partial: "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
  paid: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
  overdue: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
  planned: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  active: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
  on_hold: "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
  resolved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
  closed: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
  // priorities
  low: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  medium: "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300",
  high: "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
  urgent: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
};

export function StatusBadge({ value }: { value?: string | null }) {
  if (!value) return <span className="text-slate-400">—</span>;
  const cls = badgePalette[value] || "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
  return <span className={clsx("badge capitalize", cls)}>{value.replace(/_/g, " ")}</span>;
}

export function Avatar({
  first,
  last,
  size = 28,
}: {
  first?: string | null;
  last?: string | null;
  size?: number;
}) {
  return (
    <span
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      className="inline-flex shrink-0 items-center justify-center rounded-full bg-primary-100 font-semibold text-primary-700 dark:bg-primary-900/60 dark:text-primary-300"
      title={`${first ?? ""} ${last ?? ""}`.trim()}
    >
      {initials(first, last)}
    </span>
  );
}

export function EmptyState({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 py-16 text-center">
      <div className="text-3xl">🗂️</div>
      <p className="font-medium text-slate-600 dark:text-slate-300">{title}</p>
      {subtitle && <p className="text-sm text-slate-400">{subtitle}</p>}
    </div>
  );
}
