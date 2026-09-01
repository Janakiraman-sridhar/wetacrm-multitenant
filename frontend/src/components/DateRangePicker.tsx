import clsx from "clsx";
import { CalendarDays, Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { DatePicker } from "@/components/DatePicker";

export const RANGE_PRESETS = [
  { key: "today", label: "Today" },
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
  { key: "month", label: "This month" },
  { key: "quarter", label: "This quarter" },
  { key: "year", label: "This year" },
  { key: "12m", label: "Last 12 months" },
] as const;

export type PresetKey = (typeof RANGE_PRESETS)[number]["key"] | "custom";

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function presetRange(preset: PresetKey): { start: string; end: string } {
  const now = new Date();
  const end = iso(now);
  switch (preset) {
    case "today":
      return { start: end, end };
    case "7d":
      return { start: iso(new Date(now.getTime() - 6 * 86400000)), end };
    case "30d":
      return { start: iso(new Date(now.getTime() - 29 * 86400000)), end };
    case "month":
      return { start: iso(new Date(now.getFullYear(), now.getMonth(), 1)), end };
    case "quarter":
      return { start: iso(new Date(now.getFullYear(), Math.floor(now.getMonth() / 3) * 3, 1)), end };
    case "year":
      return { start: iso(new Date(now.getFullYear(), 0, 1)), end };
    default:
      return { start: iso(new Date(now.getFullYear() - 1, now.getMonth(), now.getDate())), end };
  }
}

function shortDate(value: string): string {
  const d = new Date(`${value}T00:00:00`);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function DateRangePicker({
  preset,
  start,
  end,
  onChange,
}: {
  preset: PresetKey;
  start: string;
  end: string;
  onChange: (preset: PresetKey, start: string, end: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draftStart, setDraftStart] = useState(start);
  const [draftEnd, setDraftEnd] = useState(end);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setDraftStart(start);
      setDraftEnd(end);
    }
  }, [open, start, end]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const activeLabel = preset === "custom" ? "Custom range" : RANGE_PRESETS.find((p) => p.key === preset)?.label;
  const customValid = !!draftStart && !!draftEnd && draftStart <= draftEnd;

  return (
    <div ref={boxRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2.5 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm shadow-sm transition-colors hover:border-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500/40 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-slate-600"
      >
        <CalendarDays size={16} className="shrink-0 text-primary-600 dark:text-primary-400" />
        <span className="font-medium">{activeLabel}</span>
        <span className="hidden text-slate-400 sm:inline">
          {shortDate(start)} – {shortDate(end)}
        </span>
        <ChevronDown size={15} className={clsx("shrink-0 text-slate-400 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="card absolute right-0 top-full z-40 mt-2 flex w-[26rem] max-w-[calc(100vw-2rem)] shadow-xl">
          <div className="w-40 shrink-0 border-r border-slate-200 p-1.5 dark:border-slate-800">
            {RANGE_PRESETS.map((p) => (
              <button
                key={p.key}
                onClick={() => {
                  const r = presetRange(p.key);
                  onChange(p.key, r.start, r.end);
                  setOpen(false);
                }}
                className={clsx(
                  "flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors",
                  preset === p.key
                    ? "bg-primary-50 font-medium text-primary-700 dark:bg-primary-900/40 dark:text-primary-300"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                )}
              >
                {p.label}
                {preset === p.key && <Check size={14} />}
              </button>
            ))}
          </div>

          <div className="flex flex-1 flex-col gap-3 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Custom range</p>
            <div>
              <label className="label">From</label>
              <DatePicker value={draftStart} onChange={setDraftStart} align="right" clearable={false} />
            </div>
            <div>
              <label className="label">To</label>
              <DatePicker value={draftEnd} onChange={setDraftEnd} align="right" clearable={false} />
            </div>
            {!customValid && draftStart && draftEnd && (
              <p className="text-xs text-red-500">"From" must be on or before "To".</p>
            )}
            <button
              className="btn-primary mt-auto"
              disabled={!customValid}
              onClick={() => {
                onChange("custom", draftStart, draftEnd);
                setOpen(false);
              }}
            >
              Apply range
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
