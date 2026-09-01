import clsx from "clsx";
import { CalendarDays, ChevronLeft, ChevronRight, Clock, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function parseValue(value: string): { date: Date | null; time: string } {
  if (!value) return { date: null, time: "" };
  const [datePart, timePart] = value.split("T");
  const d = new Date(`${datePart}T00:00:00`);
  if (Number.isNaN(d.getTime())) return { date: null, time: "" };
  return { date: d, time: timePart?.slice(0, 5) ?? "" };
}

/**
 * Styled date / date-time picker used for every date field in the app.
 * Values are plain strings ("YYYY-MM-DD" or "YYYY-MM-DDTHH:mm") so it's a
 * drop-in replacement for native date inputs in the forms and the API.
 */
export function DatePicker({
  value,
  onChange,
  mode = "date",
  placeholder,
  error = false,
  clearable = true,
  align = "left",
  id,
}: {
  value: string;
  onChange: (value: string) => void;
  mode?: "date" | "datetime";
  placeholder?: string;
  error?: boolean;
  clearable?: boolean;
  align?: "left" | "right";
  id?: string;
}) {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const { date: selected, time } = useMemo(() => parseValue(value), [value]);
  const [cursor, setCursor] = useState<Date>(() => selected ?? new Date());

  useEffect(() => {
    if (open) setCursor(selected ?? new Date());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
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

  const label = useMemo(() => {
    if (!selected) return "";
    const d = selected.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    return mode === "datetime" && time ? `${d} · ${time}` : d;
  }, [selected, time, mode]);

  const weeks = useMemo(() => {
    const monthStart = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
    const lead = (monthStart.getDay() + 6) % 7; // Monday-first
    const cells: (Date | null)[] = [
      ...Array.from({ length: lead }, () => null),
      ...Array.from({ length: daysInMonth }, (_, i) => new Date(cursor.getFullYear(), cursor.getMonth(), i + 1)),
    ];
    while (cells.length % 7 !== 0) cells.push(null);
    const rows: (Date | null)[][] = [];
    for (let i = 0; i < cells.length; i += 7) rows.push(cells.slice(i, i + 7));
    return rows;
  }, [cursor]);

  const todayStr = toDateStr(new Date());
  const selectedStr = selected ? toDateStr(selected) : "";

  const pickDay = (day: Date) => {
    if (mode === "date") {
      onChange(toDateStr(day));
      setOpen(false);
    } else {
      onChange(`${toDateStr(day)}T${time || "09:00"}`);
    }
  };

  const pickTime = (t: string) => {
    if (!t) return;
    onChange(`${toDateStr(selected ?? new Date())}T${t}`);
  };

  const monthLabel = cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        id={id}
        onClick={() => setOpen(!open)}
        className={clsx(
          "flex w-full items-center gap-2 rounded-lg border bg-white px-3 py-2 text-left text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500/30 dark:bg-slate-900",
          error
            ? "border-red-400 dark:border-red-700"
            : "border-slate-300 hover:border-slate-400 focus:border-primary-500 dark:border-slate-700 dark:hover:border-slate-600",
          open && "border-primary-500 ring-2 ring-primary-500/30 dark:border-primary-500"
        )}
      >
        <CalendarDays size={15} className="shrink-0 text-primary-600 dark:text-primary-400" />
        <span className={clsx("flex-1 truncate", !label && "text-slate-400")}>
          {label || placeholder || (mode === "datetime" ? "Pick date & time…" : "Pick a date…")}
        </span>
        {clearable && label && (
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
            <X size={13} />
          </span>
        )}
      </button>

      {open && (
        <div
          className={clsx(
            "absolute z-50 mt-1.5 w-[17rem] rounded-xl border border-slate-200 bg-white p-3 shadow-xl dark:border-slate-700 dark:bg-slate-900",
            align === "right" ? "right-0" : "left-0"
          )}
        >
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              className="btn-ghost !p-1.5"
              onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
            >
              <ChevronLeft size={15} />
            </button>
            <span className="text-sm font-semibold">{monthLabel}</span>
            <button
              type="button"
              className="btn-ghost !p-1.5"
              onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
            >
              <ChevronRight size={15} />
            </button>
          </div>

          <div className="grid grid-cols-7 gap-0.5 text-center">
            {WEEKDAYS.map((d) => (
              <span key={d} className="py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                {d}
              </span>
            ))}
            {weeks.flat().map((day, i) => {
              if (!day) return <span key={i} />;
              const dayStr = toDateStr(day);
              const isSelected = dayStr === selectedStr;
              const isToday = dayStr === todayStr;
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => pickDay(day)}
                  className={clsx(
                    "mx-auto flex h-8 w-8 items-center justify-center rounded-lg text-sm transition-colors",
                    isSelected
                      ? "bg-primary-600 font-semibold text-white"
                      : isToday
                        ? "font-semibold text-primary-600 ring-1 ring-inset ring-primary-300 dark:text-primary-400 dark:ring-primary-700"
                        : "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                  )}
                >
                  {day.getDate()}
                </button>
              );
            })}
          </div>

          {mode === "datetime" && (
            <div className="mt-2.5 flex items-center gap-2 border-t border-slate-100 pt-2.5 dark:border-slate-800">
              <Clock size={14} className="shrink-0 text-slate-400" />
              <input
                type="time"
                className="input !py-1.5 text-sm"
                value={time}
                onChange={(e) => pickTime(e.target.value)}
              />
              <button type="button" className="btn-primary !py-1.5" onClick={() => setOpen(false)}>
                Done
              </button>
            </div>
          )}

          <div className="mt-2.5 flex items-center justify-between border-t border-slate-100 pt-2 dark:border-slate-800">
            <button
              type="button"
              className="text-xs font-medium text-primary-600 hover:underline dark:text-primary-400"
              onClick={() => {
                const now = new Date();
                onChange(mode === "date" ? toDateStr(now) : `${toDateStr(now)}T${pad(now.getHours())}:${pad(now.getMinutes())}`);
                if (mode === "date") setOpen(false);
                else setCursor(now);
              }}
            >
              {mode === "datetime" ? "Now" : "Today"}
            </button>
            {clearable && (
              <button
                type="button"
                className="text-xs text-slate-400 hover:text-slate-600 hover:underline dark:hover:text-slate-300"
                onClick={() => {
                  onChange("");
                  setOpen(false);
                }}
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
