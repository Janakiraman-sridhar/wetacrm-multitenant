import clsx from "clsx";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

export interface Option {
  value: string;
  label: string;
}

/** Multi-select dropdown with a checklist + search; value is an array of values. */
export function MultiSelect({
  value,
  onChange,
  options,
  placeholder = "Any",
}: {
  value: string[];
  onChange: (value: string[]) => void;
  options: Option[];
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);
  const showSearch = options.length > 7;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
  }, [options, query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  const toggle = (v: string) => {
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  };

  const selectedLabels = value
    .map((v) => options.find((o) => o.value === v)?.label)
    .filter(Boolean) as string[];

  const summary =
    selectedLabels.length === 0
      ? placeholder
      : selectedLabels.length === 1
        ? selectedLabels[0]
        : `${selectedLabels.length} selected`;

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={clsx(
          "flex w-full items-center justify-between gap-2 rounded-lg border bg-white px-3 py-2 text-left text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500/30 dark:bg-slate-900",
          value.length
            ? "border-primary-300 dark:border-primary-800"
            : "border-slate-300 hover:border-slate-400 dark:border-slate-700 dark:hover:border-slate-600",
          open && "border-primary-500 ring-2 ring-primary-500/30 dark:border-primary-500"
        )}
      >
        <span className={clsx("truncate", value.length === 0 && "text-slate-400")}>{summary}</span>
        <span className="flex shrink-0 items-center gap-1">
          {value.length > 0 && (
            <span
              role="button"
              tabIndex={-1}
              className="rounded p-0.5 text-slate-300 hover:bg-slate-100 hover:text-slate-500 dark:hover:bg-slate-800"
              onClick={(e) => {
                e.stopPropagation();
                onChange([]);
              }}
              title="Clear"
            >
              <X size={13} />
            </span>
          )}
          <ChevronDown size={15} className={clsx("text-slate-400 transition-transform", open && "rotate-180")} />
        </span>
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-1.5 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
          {showSearch && (
            <div className="relative border-b border-slate-100 p-1.5 dark:border-slate-800">
              <Search size={13} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                autoFocus
                className="w-full rounded-md bg-slate-50 py-1.5 pl-8 pr-2 text-sm placeholder-slate-400 focus:outline-none dark:bg-slate-800"
                placeholder="Search…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
          )}
          <div className="max-h-52 overflow-y-auto p-1">
            {filtered.length === 0 && <p className="px-2.5 py-3 text-center text-xs text-slate-400">No matches</p>}
            {filtered.map((o) => {
              const checked = value.includes(o.value);
              return (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => toggle(o.value)}
                  className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  <span
                    className={clsx(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                      checked
                        ? "border-primary-600 bg-primary-600 text-white"
                        : "border-slate-300 dark:border-slate-600"
                    )}
                  >
                    {checked && <Check size={11} />}
                  </span>
                  <span className="truncate">{o.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
