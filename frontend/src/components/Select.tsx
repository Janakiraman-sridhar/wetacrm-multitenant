import clsx from "clsx";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

export interface SelectOption {
  value: string;
  label: string;
}

/**
 * Custom dropdown used across forms and toolbars: styled trigger, popover
 * listbox with optional search, checkmark on the active option, clearable.
 */
export function Select({
  value,
  onChange,
  options,
  placeholder = "Select…",
  clearable = true,
  searchable,
  compact = false,
  error = false,
  direction = "down",
  id,
}: {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  clearable?: boolean;
  searchable?: boolean;
  compact?: boolean;
  error?: boolean;
  direction?: "down" | "up";
  id?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const showSearch = searchable ?? options.length > 7;
  const selected = options.find((o) => o.value === value);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
  }, [options, query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setTimeout(() => searchRef.current?.focus(), 0);
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

  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
  };

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        id={id}
        onClick={() => setOpen(!open)}
        className={clsx(
          "flex w-full items-center justify-between gap-2 rounded-lg border bg-white text-left transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500/30 dark:bg-slate-900",
          compact ? "px-2.5 py-1.5 text-xs" : "px-3 py-2 text-sm",
          error
            ? "border-red-400 dark:border-red-700"
            : "border-slate-300 hover:border-slate-400 focus:border-primary-500 dark:border-slate-700 dark:hover:border-slate-600",
          open && "border-primary-500 ring-2 ring-primary-500/30 dark:border-primary-500"
        )}
      >
        <span className={clsx("truncate", !selected && "text-slate-400")}>{selected?.label ?? placeholder}</span>
        <span className="flex shrink-0 items-center gap-1">
          {clearable && selected && (
            <span
              role="button"
              tabIndex={-1}
              className="rounded p-0.5 text-slate-300 hover:bg-slate-100 hover:text-slate-500 dark:hover:bg-slate-800"
              onClick={(e) => {
                e.stopPropagation();
                onChange("");
                setOpen(false);
              }}
              title="Clear"
            >
              <X size={compact ? 11 : 13} />
            </span>
          )}
          <ChevronDown
            size={compact ? 13 : 15}
            className={clsx("text-slate-400 transition-transform", open && "rotate-180")}
          />
        </span>
      </button>

      {open && (
        <div
          className={clsx(
            "absolute left-0 z-50 min-w-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900",
            direction === "up" ? "bottom-full mb-1.5" : "top-full mt-1.5"
          )}
        >
          {showSearch && (
            <div className="relative border-b border-slate-100 p-1.5 dark:border-slate-800">
              <Search size={13} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                ref={searchRef}
                className="w-full rounded-md bg-slate-50 py-1.5 pl-8 pr-2 text-sm placeholder-slate-400 focus:outline-none dark:bg-slate-800"
                placeholder="Search…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
          )}
          <div className="max-h-56 overflow-y-auto p-1">
            {clearable && !query && (
              <button
                type="button"
                onClick={() => pick("")}
                className="flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-sm italic text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                None
                {!value && <Check size={13} className="text-primary-600" />}
              </button>
            )}
            {filtered.length === 0 && <p className="px-2.5 py-3 text-center text-xs text-slate-400">No matches</p>}
            {filtered.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => pick(option.value)}
                className={clsx(
                  "flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
                  option.value === value
                    ? "bg-primary-50 font-medium text-primary-700 dark:bg-primary-900/40 dark:text-primary-300"
                    : "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                )}
              >
                <span className="truncate">{option.label}</span>
                {option.value === value && <Check size={13} className="shrink-0" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
