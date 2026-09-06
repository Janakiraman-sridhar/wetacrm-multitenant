import clsx from "clsx";
import { X } from "lucide-react";

import { DatePicker } from "@/components/DatePicker";
import { MultiSelect } from "@/components/MultiSelect";
import { Select } from "@/components/Select";
import { ActiveFilter, countActive, FilterFieldDef, isFilterActive } from "@/lib/filters";

const NUMBER_OPS = [
  { value: "gte", label: "≥ at least" },
  { value: "lte", label: "≤ at most" },
  { value: "eq", label: "= exactly" },
];

/** Inline, expandable filter panel. Applies live as the user edits. */
export function FiltersBar({
  fields,
  value,
  onChange,
}: {
  fields: FilterFieldDef[];
  value: ActiveFilter[];
  onChange: (filters: ActiveFilter[]) => void;
}) {
  const byKey = (key: string) => value.find((f) => f.key === key);

  const setFilter = (key: string, next: Partial<ActiveFilter> | null) => {
    const field = fields.find((f) => f.key === key)!;
    const others = value.filter((f) => f.key !== key);
    if (next === null) {
      onChange(others);
      return;
    }
    const existing = byKey(key) ?? { key, type: field.type };
    onChange([...others, { ...existing, ...next }]);
  };

  const active = countActive(value);

  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Filters {active > 0 && <span className="text-primary-600 dark:text-primary-400">· {active} active</span>}
        </span>
        {active > 0 && (
          <button
            className="text-xs font-medium text-slate-400 hover:text-red-500"
            onClick={() => onChange([])}
          >
            Clear all
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-x-5 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        {fields.map((field) => {
          const current = byKey(field.key);
          const isOn = isFilterActive(current);
          return (
            <div key={field.key}>
              <label
                className={clsx(
                  "mb-1 block text-xs font-semibold",
                  isOn ? "text-primary-600 dark:text-primary-400" : "text-slate-500 dark:text-slate-400"
                )}
              >
                {field.label}
              </label>

              {field.type === "text" && (
                <input
                  className="input !py-2"
                  placeholder={`Filter by ${field.label.toLowerCase()}…`}
                  value={current?.value ?? ""}
                  onChange={(e) => setFilter(field.key, e.target.value ? { value: e.target.value } : null)}
                />
              )}

              {field.type === "select" && (
                <MultiSelect
                  options={field.options ?? []}
                  value={current?.value ?? []}
                  onChange={(v) => setFilter(field.key, v.length ? { value: v } : null)}
                />
              )}

              {field.type === "number" && (
                <div className="flex gap-2">
                  <span className="w-28 shrink-0">
                    <Select
                      compact={false}
                      clearable={false}
                      searchable={false}
                      value={current?.op ?? "gte"}
                      onChange={(op) => setFilter(field.key, { op: op as any, value: current?.value })}
                      options={NUMBER_OPS}
                    />
                  </span>
                  <input
                    type="number"
                    className="input !py-2"
                    placeholder="value"
                    value={current?.value ?? ""}
                    onChange={(e) =>
                      setFilter(
                        field.key,
                        e.target.value !== "" ? { value: e.target.value, op: current?.op ?? "gte" } : null
                      )
                    }
                  />
                </div>
              )}

              {field.type === "date" && (
                <div className="flex items-center gap-2">
                  <DatePicker
                    value={current?.from ?? ""}
                    placeholder="From"
                    onChange={(from) =>
                      setFilter(field.key, from || current?.to ? { from, to: current?.to } : null)
                    }
                  />
                  <span className="text-slate-400">–</span>
                  <DatePicker
                    value={current?.to ?? ""}
                    placeholder="To"
                    align="right"
                    onChange={(to) =>
                      setFilter(field.key, to || current?.from ? { from: current?.from, to } : null)
                    }
                  />
                </div>
              )}

              {isOn && (
                <button
                  className="mt-1 inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-red-500"
                  onClick={() => setFilter(field.key, null)}
                >
                  <X size={11} /> clear
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
