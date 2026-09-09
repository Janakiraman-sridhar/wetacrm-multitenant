import clsx from "clsx";
import { GripVertical, Lock, Plus, RotateCcw, Search, X } from "lucide-react";
import { useMemo, useState } from "react";

import { moduleIcon } from "@/lib/modules";

export interface CatalogModule {
  key: string;
  label: string;
  order: number;
  icon: string;
  locked: boolean;
  permission?: string | null;
}

export interface ModuleSetting {
  key: string;
  enabled: boolean;
  label?: string | null;
  order?: number;
}

/**
 * Choose what a workspace gets, by building the sidebar its users will see.
 *
 * The previous version listed all eighteen catalog modules in one flat column with
 * a checkbox at the far right of each row, which made the decision that matters —
 * *which modules does this client get* — the least prominent thing on screen, and
 * made the outcome impossible to picture. Here the left column simply **is** the
 * sidebar: the modules that are on, in the order they will appear, under the names
 * this client will read. Nothing is drawn twice and nothing has to be imagined.
 *
 * The drag handle drags. The old one was a `GripVertical` next to a pair of arrow
 * buttons, and dragging did nothing at all — a control that lies about what it can
 * do costs more than no control.
 */
export function ModuleBoard({
  catalog,
  value,
  onChange,
  disabled = false,
}: {
  catalog: CatalogModule[];
  value: ModuleSetting[];
  onChange: (next: ModuleSetting[]) => void;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [dragKey, setDragKey] = useState<string | null>(null);

  const defaults = useMemo(
    () => new Map(catalog.map((c) => [c.key, c])),
    [catalog]
  );

  const included = value.filter((m) => m.enabled);
  const excluded = value.filter((m) => !m.enabled);

  const matches = (m: ModuleSetting) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    const base = defaults.get(m.key);
    return (
      m.key.includes(needle) ||
      (m.label ?? "").toLowerCase().includes(needle) ||
      (base?.label ?? "").toLowerCase().includes(needle)
    );
  };

  const patch = (key: string, changes: Partial<ModuleSetting>) =>
    onChange(value.map((m) => (m.key === key ? { ...m, ...changes } : m)));

  /** Adding puts it at the end of the sidebar, where a new thing belongs. */
  const include = (key: string) => {
    const rest = value.filter((m) => m.key !== key);
    const found = value.find((m) => m.key === key)!;
    onChange([...rest.filter((m) => m.enabled), { ...found, enabled: true },
              ...rest.filter((m) => !m.enabled)]);
  };

  const exclude = (key: string) => {
    const found = value.find((m) => m.key === key)!;
    const rest = value.filter((m) => m.key !== key);
    onChange([...rest.filter((m) => m.enabled), { ...found, enabled: false },
              ...rest.filter((m) => !m.enabled)]);
  };

  /** Reorder within the included list; the excluded ones keep their own order. */
  const dropOn = (targetKey: string) => {
    if (!dragKey || dragKey === targetKey) return;
    const order = included.map((m) => m.key);
    const from = order.indexOf(dragKey);
    const to = order.indexOf(targetKey);
    if (from < 0 || to < 0) return;
    order.splice(to, 0, ...order.splice(from, 1));
    const byKey = new Map(value.map((m) => [m.key, m]));
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
          modules included
        </p>
        <div className="relative w-full min-w-0 sm:w-56">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            className="input !pl-8 !py-1.5 text-sm"
            placeholder="Find a module…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,17rem)]">
        {/* The sidebar this client will actually see. */}
        <section className="card overflow-hidden">
          <header className="border-b border-slate-100 bg-slate-50/70 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/40">
            <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Their sidebar{disabled ? "" : " · drag to reorder"}
            </h4>
          </header>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {included.filter(matches).map((m) => {
              const base = defaults.get(m.key);
              const Icon = moduleIcon(base?.icon ?? "Circle");
              const renamed = !!m.label && m.label !== base?.label;
              return (
                <li
                  key={m.key}
                  draggable={!disabled && !query}
                  onDragStart={() => setDragKey(m.key)}
                  onDragEnd={() => setDragKey(null)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => dropOn(m.key)}
                  className={clsx(
                    "flex items-center gap-2 px-2.5 py-2 transition-colors",
                    !disabled && !query && "cursor-grab active:cursor-grabbing",
                    dragKey === m.key && "opacity-40"
                  )}
                >
                  {!disabled && (
                    <GripVertical
                      size={14}
                      className={clsx(
                        "shrink-0",
                        query ? "text-slate-200 dark:text-slate-700" : "text-slate-300 dark:text-slate-600"
                      )}
                    />
                  )}
                  <Icon size={16} className="shrink-0 text-primary-600 dark:text-primary-400" />
                  <input
                    className="input !border-transparent !bg-transparent !px-1.5 !py-1 text-sm hover:!border-slate-200 focus:!border-primary-500 focus:!bg-white dark:hover:!border-slate-700 dark:focus:!bg-slate-900"
                    value={m.label ?? ""}
                    placeholder={base?.label ?? m.key}
                    disabled={disabled}
                    aria-label={`What ${base?.label ?? m.key} is called here`}
                    onChange={(e) => patch(m.key, { label: e.target.value })}
                  />
                  {renamed && !disabled && (
                    <button
                      className="btn-ghost !p-1 text-slate-400"
                      title={`Call it "${base?.label}" again`}
                      onClick={() => patch(m.key, { label: base?.label })}
                    >
                      <RotateCcw size={12} />
                    </button>
                  )}
                  {base?.locked ? (
                    <span
                      className="flex shrink-0 items-center gap-1 px-1.5 text-[11px] text-slate-400"
                      title="Every workspace needs this one — it cannot be removed"
                    >
                      <Lock size={11} /> always
                    </span>
                  ) : disabled ? null : (
                    <button
                      className="btn-ghost !p-1 shrink-0 text-slate-400 hover:text-red-500"
                      title="Remove from this workspace"
                      onClick={() => exclude(m.key)}
                    >
                      <X size={14} />
                    </button>
                  )}
                </li>
              );
            })}
            {included.filter(matches).length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-slate-400">
                {query ? "Nothing included matches that." : "No modules — this workspace would be empty."}
              </li>
            )}
          </ul>
        </section>

        {/* Everything switched off, so it is obvious what is being withheld. */}
        <section className="card overflow-hidden">
          <header className="border-b border-slate-100 bg-slate-50/70 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/40">
            <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Not included
            </h4>
          </header>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {excluded.filter(matches).map((m) => {
              const base = defaults.get(m.key);
              const Icon = moduleIcon(base?.icon ?? "Circle");
              return (
                <li key={m.key} className="flex items-center gap-2 px-2.5 py-2">
                  <Icon size={15} className="shrink-0 text-slate-300 dark:text-slate-600" />
                  <span className="min-w-0 flex-1 truncate text-sm text-slate-500 dark:text-slate-400">
                    {base?.label ?? m.key}
                  </span>
                  {!disabled && (
                    <button
                      className="btn-ghost !px-1.5 !py-1 shrink-0 text-xs text-primary-600 dark:text-primary-400"
                      title="Add to this workspace"
                      onClick={() => include(m.key)}
                    >
                      <Plus size={13} /> Add
                    </button>
                  )}
                </li>
              );
            })}
            {excluded.filter(matches).length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-slate-400">
                {query ? "Nothing excluded matches that." : "Everything is included."}
              </li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}

/**
 * Merge a stored module list with the catalog, the way provisioning will read it.
 *
 * `_apply_modules` treats a template that names **any** module as naming all of
 * them, so anything left out is off. The editor used to default an unnamed module
 * to *on*, which had two consequences and both were live: it showed sixteen modules
 * included for a template that grants five, and pressing Save wrote that back —
 * silently switching on eleven modules the template deliberately withheld.
 */
export function mergeWithCatalog(
  catalog: CatalogModule[],
  configured: ModuleSetting[] | null | undefined
): ModuleSetting[] {
  const named = new Map((configured ?? []).map((m) => [m.key, m]));
  const selective = named.size > 0;

  return catalog
    .map((entry) => {
      const override = named.get(entry.key);
      return {
        key: entry.key,
        enabled: entry.locked ? true : override ? override.enabled : !selective,
        label: override?.label || entry.label,
        order: override?.order ?? entry.order,
      };
    })
    .sort((a, b) => (a.order ?? 99) - (b.order ?? 99));
}
