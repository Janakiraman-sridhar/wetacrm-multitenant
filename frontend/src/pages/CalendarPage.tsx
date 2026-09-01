import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldDef, FormFields } from "@/components/CrudPage";
import { Modal } from "@/components/Modal";
import { PageSpinner } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { optStr, reqStr } from "@/lib/zh";
import type { CalendarItem } from "@/types";

const TYPE_TONES: Record<string, string> = {
  meeting: "bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300",
  call: "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300",
  follow_up: "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
  reminder: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

const schema = z.object({
  title: reqStr("Title is required"),
  kind: z.string(),
  starts_at: reqStr("Start time is required"),
  ends_at: optStr,
  location: optStr,
  notes: optStr,
});

export default function CalendarPage() {
  const { hasPerm } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [cursor, setCursor] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [modalOpen, setModalOpen] = useState(false);

  const monthStart = cursor;
  const monthEnd = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0, 23, 59, 59);

  const { data, isLoading } = useQuery({
    queryKey: ["calendar", cursor.toISOString()],
    queryFn: async () =>
      (
        await api.get<CalendarItem[]>("/calendar", {
          params: { start: monthStart.toISOString().slice(0, 19), end: monthEnd.toISOString().slice(0, 19) },
        })
      ).data,
  });

  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: { title: "", kind: "meeting", starts_at: "", ends_at: "", location: "", notes: "" },
  });

  const createMutation = useMutation({
    mutationFn: async (values: any) => {
      if (values.kind === "meeting") {
        return (
          await api.post("/meetings", {
            title: values.title,
            starts_at: values.starts_at,
            ends_at: values.ends_at || null,
            location: values.location || null,
            agenda: values.notes || null,
          })
        ).data;
      }
      return (
        await api.post("/calendar/events", {
          title: values.title,
          type: values.kind,
          starts_at: values.starts_at,
          ends_at: values.ends_at || null,
          notes: values.notes || null,
        })
      ).data;
    },
    onSuccess: () => {
      toast("Added to calendar");
      setModalOpen(false);
      form.reset();
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const byDay = useMemo(() => {
    const map: Record<string, CalendarItem[]> = {};
    for (const item of data ?? []) {
      const key = item.starts_at.slice(0, 10);
      (map[key] = map[key] ?? []).push(item);
    }
    return map;
  }, [data]);

  const weeks = useMemo(() => {
    const firstWeekday = (monthStart.getDay() + 6) % 7; // Monday-first
    const daysInMonth = monthEnd.getDate();
    const cells: (Date | null)[] = [
      ...Array.from({ length: firstWeekday }, () => null),
      ...Array.from({ length: daysInMonth }, (_, i) => new Date(cursor.getFullYear(), cursor.getMonth(), i + 1)),
    ];
    while (cells.length % 7 !== 0) cells.push(null);
    const rows: (Date | null)[][] = [];
    for (let i = 0; i < cells.length; i += 7) rows.push(cells.slice(i, i + 7));
    return rows;
  }, [cursor, monthEnd, monthStart]);

  const todayKey = new Date().toISOString().slice(0, 10);
  const monthLabel = cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  const fields: FieldDef[] = [
    { name: "title", label: "Title", colSpan: 2 },
    {
      name: "kind",
      label: "Type",
      type: "select",
      options: [
        { value: "meeting", label: "Meeting" },
        { value: "call", label: "Call" },
        { value: "follow_up", label: "Follow-up" },
        { value: "reminder", label: "Reminder" },
      ],
    },
    { name: "location", label: "Location / link" },
    { name: "starts_at", label: "Starts", type: "datetime-local" },
    { name: "ends_at", label: "Ends", type: "datetime-local" },
    { name: "notes", label: "Notes / agenda", type: "textarea", colSpan: 2 },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Calendar</h1>
        <div className="flex items-center gap-2">
          <button
            className="btn-ghost !p-2"
            onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
          >
            <ChevronLeft size={16} />
          </button>
          <span className="w-40 text-center font-medium">{monthLabel}</span>
          <button
            className="btn-ghost !p-2"
            onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
          >
            <ChevronRight size={16} />
          </button>
          {hasPerm("calendar:write") && (
            <button className="btn-primary" onClick={() => setModalOpen(true)}>
              <Plus size={16} /> Add
            </button>
          )}
        </div>
      </div>

      {isLoading ? (
        <PageSpinner />
      ) : (
        <div className="card overflow-hidden">
          <div className="grid grid-cols-7 border-b border-slate-200 text-center text-xs font-semibold uppercase tracking-wide text-slate-400 dark:border-slate-800">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
              <div key={d} className="py-2">
                {d}
              </div>
            ))}
          </div>
          {weeks.map((week, wi) => (
            <div key={wi} className="grid grid-cols-7">
              {week.map((day, di) => {
                const key = day?.toISOString().slice(0, 10);
                const items = key ? (byDay[key] ?? []) : [];
                return (
                  <div
                    key={di}
                    className={clsx(
                      "min-h-24 border-b border-r border-slate-100 p-1.5 last:border-r-0 dark:border-slate-800",
                      !day && "bg-slate-50/60 dark:bg-slate-900/40"
                    )}
                  >
                    {day && (
                      <>
                        <span
                          className={clsx(
                            "inline-flex h-6 w-6 items-center justify-center rounded-full text-xs",
                            key === todayKey ? "bg-primary-600 font-bold text-white" : "text-slate-500"
                          )}
                        >
                          {day.getDate()}
                        </span>
                        <div className="mt-1 space-y-1">
                          {items.slice(0, 3).map((item) => (
                            <div
                              key={`${item.kind}-${item.id}`}
                              className={clsx("truncate rounded px-1.5 py-0.5 text-[11px] font-medium", TYPE_TONES[item.type])}
                              title={`${item.title} · ${new Date(item.starts_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
                            >
                              {new Date(item.starts_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}{" "}
                              {item.title}
                            </div>
                          ))}
                          {items.length > 3 && (
                            <p className="px-1 text-[10px] text-slate-400">+{items.length - 3} more</p>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Add to calendar">
        <form onSubmit={form.handleSubmit((v) => createMutation.mutate(v))} className="space-y-5">
          <FormFields fields={fields} register={form.register} errors={form.formState.errors} />
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setModalOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
