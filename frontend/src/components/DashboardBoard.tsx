import clsx from "clsx";
import { GripVertical, Lock, Plus, Search, X } from "lucide-react";
import { useState } from "react";

import type { DashboardWidget } from "@/lib/dashboard";

export interface WidgetSetting {
  key: string;
  enabled: boolean;
  order?: number;
}

/**
 * Choose what a dashboard opens on, by building it.
 *
 * The same two-column shape as `ModuleBoard`, deliberately: choosing a workspace's
 * modules and choosing its dashboard are the same kind of decision, and an admin
 * should not have two interactions to learn. Left is the dashboard in the order it
 * will be read; right is what is being left off.
 *
 * A card whose module is switched off is not offered at all — it is shown greyed
 * with the reason, because "why can't I add Renewals due" has a real answer and
 * hiding the card entirely does not give it.
 */
export function DashboardBoard({
  catalog,
  value,
  onChange,
  enabledModules,
  disabled = false,
}: {
  catalog: DashboardWidget[];
  value: WidgetSetting[];
  onChange: (next: WidgetSetting[]) => void;
  /** Module keys this workspace has on. Omit when choosing for a template. */
  enabledModules?: Set<string>;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [dragKey, setDragKey] = useState<string | null>(null);

  const defs = new Map(catalog.map((c) => [c.key, c]));
  const available = (key: string) => {
    const def = defs.get(key);
    if (!def?.requires || !enabledModules) return true;
    return enabledModules.has(def.requires);
  };

  const included = value.filter((w) => w.enabled && available(w.key));
  const excluded = value.filter((w) => !w.enabled || !available(w.key));

  const matches = (w: WidgetSetting) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    const def = defs.get(w.key);
    return (
      w.key.includes(needle) ||
      (def?.label ?? "").toLowerCase().includes(needle) ||
      (def?.description ?? "").toLowerCase().includes(needle)
    );
  };

  const include = (key: string) => {
    const found = value.find((w) => w.key === key)!;
    const rest = value.filter((w) => w.key !== key);
    onChange([...rest.filter((w) => w.enabled), { ...found, enabled: true },
              ...rest.filter((w) => !w.enabled)]);
  };

  const exclude = (key: string) => {
    const found = value.find((w) => w.key === key)!;
    const rest = value.filter((w) => w.key !== key);
    onChange([...rest.filter((w) => w.enabled), { ...found, enabled: false },
              ...rest.filter((w) => !w.enabled)]);
  };

  const dropOn = (targetKey: string) => {
    if (!dragKey || dragKey === targetKey) return;
    const order = included.map((w) => w.key);
    const from = order.indexOf(dragKey);
    const to = order.indexOf(targetKey);
    if (from < 0 || to < 0) return;
    order.splice(to, 0, ...order.splice(from, 1));
    const byKey = new Map(value.map((w) => [w.key, w]));
    onChange([...order.map((k) => byKey.get(k)!), ...excluded]);
    setDragKey(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          <span className="font-medium text-slate-700 dark:text-slate-200">
            {included.length} of {value.length}
          </span>{" "}
          cards on the dashboard
        </p>
        <div className="relative w-full min-w-0 sm:w-56">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            className="input !pl-8 !py-1.5 text-sm"
            placeholder="Find a card…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
        <section className="card overflow-hidden">
          <header className="border-b border-slate-100 bg-slate-50/70 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/40">
            <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              On the dashboard{disabled ? "" : " · drag to reorder, top card first"}
            </h4>
          </header>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {included.filter(matches).map((w) => {
              const def = defs.get(w.key);
              return (
                <li
                  key={w.key}
                  draggable={!disabled && !query}
                  onDragStart={() => setDragKey(w.key)}
                  onDragEnd={() => setDragKey(null)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => dropOn(w.key)}
                  className={clsx(
                    "flex items-start gap-2 px-2.5 py-2 transition-colors",
                    !disabled && !query && "cursor-grab active:cursor-grabbing",
                    dragKey === w.key && "opacity-40"
                  )}
                >
                  {!disabled && (
                    <GripVertical size={14} className="mt-0.5 shrink-0 text-slate-300 dark:text-slate-600" />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="text-sm font-medium">{def?.label ?? w.key}</span>
                      {def?.width === "full" && (
                        <span className="badge bg-slate-100 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                          full width
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">
                      {def?.description}
                    </span>
                  </span>
                  {def?.locked ? (
                    <span className="flex shrink-0 items-center gap-1 px-1.5 text-[11px] text-slate-400">
                      <Lock size={11} /> always
                    </span>
                  ) : disabled ? null : (
                    <button
                      className="btn-ghost !p-1 shrink-0 text-slate-400 hover:text-red-500"
                      title="Take it off the dashboard"
                      onClick={() => exclude(w.key)}
                    >
                      <X size={14} />
                    </button>
                  )}
                </li>
              );
            })}
            {included.filter(matches).length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-slate-400">
                {query ? "Nothing on the dashboard matches that." : "Nothing on the dashboard."}
              </li>
            )}
          </ul>
        </section>

        <section className="card overflow-hidden">
          <header className="border-b border-slate-100 bg-slate-50/70 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/40">
            <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Not shown
            </h4>
          </header>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {excluded.filter(matches).map((w) => {
              const def = defs.get(w.key);
              const blocked = !available(w.key);
              return (
                <li key={w.key} className="flex items-start gap-2 px-2.5 py-2">
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm text-slate-600 dark:text-slate-300">
                      {def?.label ?? w.key}
                    </span>
                    <span className="mt-0.5 block text-xs text-slate-400">
                      {blocked
                        ? `Needs the ${def?.requires} module, which is switched off here.`
                        : def?.description}
                    </span>
                  </span>
                  {!disabled && !blocked && (
                    <button
                      className="btn-ghost !px-1.5 !py-1 shrink-0 text-xs text-primary-600 dark:text-primary-400"
                      title="Put it on the dashboard"
                      onClick={() => include(w.key)}
                    >
                      <Plus size={13} /> Add
                    </button>
                  )}
                </li>
              );
            })}
            {excluded.filter(matches).length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-slate-400">
                {query ? "Nothing hidden matches that." : "Everything is on the dashboard."}
              </li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}
