import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, CalendarClock, Lock, Users, Zap } from "lucide-react";

import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { EmailTemplate } from "@/types";

/**
 * When a template fires, and whether it does.
 *
 * The switch is the point of the whole thing: before this, the connection between a
 * template and the moment it sends was a line of code, so the workspace could edit
 * the wording of an email it had no way to stop, and could not send two templates
 * that were sitting configured and unreachable.
 *
 * Customer-facing triggers are called out in a warning colour, because the blast
 * radius of switching one on is the client's whole book of customers rather than one
 * colleague's inbox — and that difference should be visible before the click, not
 * discovered from the replies.
 */
export function EmailWorkflow({
  template,
  canWrite,
}: {
  template: EmailTemplate;
  canWrite: boolean;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const update = useMutation({
    mutationFn: async (patch: Partial<EmailTemplate>) =>
      (await api.patch(`/settings/email-templates/${template.id}`, patch)).data,
    onSuccess: (_data, patch) => {
      if ("enabled" in patch) toast(patch.enabled ? "Turned on" : "Turned off");
      else toast("Schedule updated");
      queryClient.invalidateQueries({ queryKey: ["email-templates"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  if (!template.trigger) {
    return (
      <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
        <AlertTriangle size={14} className="mt-0.5 shrink-0" />
        <span>
          Nothing sends this template. It can be edited, but no event is wired to it —
          so it will never reach anyone.
        </span>
      </div>
    );
  }

  const Icon = template.trigger_kind === "scheduled" ? CalendarClock : Zap;
  const daysField = template.config_schema?.days_before;
  const chosen: number[] = template.config?.days_before ?? daysField?.default ?? [];

  const toggleDay = (day: number) => {
    const next = chosen.includes(day)
      ? chosen.filter((d) => d !== day)
      : [...chosen, day].sort((a, b) => b - a);
    update.mutate({ config: { ...template.config, days_before: next } });
  };

  return (
    <div
      className={clsx(
        "mt-3 rounded-lg border px-3 py-2.5",
        template.enabled
          ? "border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/40"
          : "border-dashed border-slate-200 dark:border-slate-800"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-xs font-semibold">
            <Icon size={13} className="shrink-0 text-primary-600 dark:text-primary-400" />
            {template.trigger_label}
            {template.customer_facing && (
              <span
                className="badge bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
                title="This one writes to your customers, not to your team"
              >
                <Users size={9} className="mr-1" /> customers
              </span>
            )}
          </p>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            {template.trigger_description}
          </p>
          <p className="mt-0.5 text-[11px] text-slate-400">Goes to: {template.audience}</p>
        </div>

        {template.locked ? (
          <span
            className="flex shrink-0 items-center gap-1 text-[11px] text-slate-400"
            title={template.locked_reason}
          >
            <Lock size={11} /> always on
          </span>
        ) : (
          <label
            className={clsx(
              "flex shrink-0 items-center gap-2 text-xs",
              canWrite ? "cursor-pointer" : "cursor-not-allowed opacity-60"
            )}
          >
            <input
              type="checkbox"
              className="h-4 w-4 accent-primary-600"
              checked={template.enabled}
              disabled={!canWrite || update.isPending}
              onChange={(e) => update.mutate({ enabled: e.target.checked })}
            />
            {template.enabled ? "On" : "Off"}
          </label>
        )}
      </div>

      {template.enabled && daysField && (
        <div className="mt-2.5 border-t border-slate-200 pt-2.5 dark:border-slate-700/60">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            {daysField.label}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {daysField.options.map((day) => (
              <button
                key={day}
                disabled={!canWrite || update.isPending}
                onClick={() => toggleDay(day)}
                className={clsx(
                  "rounded-md border px-2 py-0.5 text-xs transition-colors",
                  chosen.includes(day)
                    ? "border-primary-500 bg-primary-600 text-white"
                    : "border-slate-300 text-slate-500 hover:border-slate-400 dark:border-slate-600 dark:text-slate-400",
                  !canWrite && "cursor-not-allowed opacity-60"
                )}
              >
                {day === 0 ? "On the day" : `${day} day${day === 1 ? "" : "s"}`}
              </button>
            ))}
          </div>
          {daysField.help && (
            <p className="mt-1.5 text-[11px] leading-snug text-slate-400">{daysField.help}</p>
          )}
        </div>
      )}

      {template.enabled && template.sent_count > 0 && (
        <p className="mt-2 text-[11px] text-slate-400">
          Sent {template.sent_count} time{template.sent_count === 1 ? "" : "s"}
          {template.last_sent_at && ` · last ${formatDateTime(template.last_sent_at)}`}
        </p>
      )}

      {!template.enabled && template.customer_facing && (
        <p className="mt-2 text-[11px] leading-snug text-slate-400">
          Off by default. Switching it on starts emailing your customers automatically —
          check the wording first.
        </p>
      )}
    </div>
  );
}
