import clsx from "clsx";
import { Eye } from "lucide-react";

export interface AuditRow {
  id: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  changes: Record<string, any>;
  ip_address?: string | null;
  created_at: string;
  user?: { first_name?: string; last_name?: string; full_name?: string } | null;
}

export const ACTION_TONES: Record<string, string> = {
  create: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  update: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  delete: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  upload: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  login: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  // Someone read a full PAN or Aadhaar. The entry that most needs to be noticed,
  // and the reason keeping this data is defensible at all.
  reveal_pii: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
};

export const actionLabel = (action: string) =>
  action === "reveal_pii" ? "viewed ID" : action.replace(/_/g, " ");

export const actorName = (p?: { first_name?: string; last_name?: string; full_name?: string } | null) =>
  p?.full_name || [p?.first_name, p?.last_name].filter(Boolean).join(" ") || "System";

/**
 * One changed field: `{"premium_gross": [12000, 14500]}` reads as "12000 → 14500".
 *
 * A create records what was made rather than a diff, so a single value is not a
 * missing half — it is the whole entry.
 */
export function Change({ field, value }: { field: string; value: any }) {
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

/** The badge shown against an entry, with the reveal case called out. */
export function ActionBadge({ action }: { action: string }) {
  return (
    <span className={clsx("badge shrink-0 gap-1", ACTION_TONES[action] ?? ACTION_TONES.login)}>
      {action === "reveal_pii" && <Eye size={10} />}
      {actionLabel(action)}
    </span>
  );
}
