import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { CalendarClock } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { WhatsAppButton } from "@/components/CustomerChip";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useValuePrivacy } from "@/lib/privacy";
import { waTemplates } from "@/lib/whatsapp";
import type { RenewalDue } from "@/types";

const RANGES = [7, 30, 60] as const;

/** The renewal desk: what expires next, and a message ready to send about it. */
export function RenewalPanel({ compact = false }: { compact?: boolean }) {
  const navigate = useNavigate();
  const { show } = useValuePrivacy();
  const [days, setDays] = useState<number>(30);

  const { data, isLoading } = useQuery({
    queryKey: ["renewals", days],
    queryFn: async () =>
      (await api.get<RenewalDue[]>("/policies/renewals", { params: { within_days: days } })).data,
    staleTime: 60_000,
  });

  const rows = data ?? [];

  return (
    <section className="card flex min-h-0 flex-col p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold">
          <CalendarClock size={16} className="text-amber-600 dark:text-amber-400" />
          Renewals due
        </h2>
        <div className="flex gap-1">
          {RANGES.map((range) => (
            <button
              key={range}
              onClick={() => setDays(range)}
              className={clsx(
                "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                days === range
                  ? "bg-amber-500 text-white"
                  : "text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
            >
              {range}d
            </button>
          ))}
        </div>
      </div>

      {isLoading && <p className="py-6 text-center text-sm text-slate-400">Loading…</p>}
      {!isLoading && rows.length === 0 && (
        <p className="py-6 text-center text-sm text-slate-400">
          Nothing expiring in the next {days} days.
        </p>
      )}

      <ul className={clsx("min-h-0 space-y-1 overflow-y-auto", compact && "max-h-72")}>
        {rows.map((policy) => (
          <li
            key={policy.id}
            className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
            onClick={() => navigate("/policies")}
          >
            <span
              className={clsx(
                "grid h-8 w-11 shrink-0 place-items-center rounded-lg text-xs font-semibold tabular-nums",
                policy.days_to_expiry <= 7
                  ? "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
                  : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
              )}
              title={`Expires ${formatDate(policy.expiry_date)}`}
            >
              {policy.days_to_expiry}d
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">
                {policy.customer?.full_name ?? "Unknown customer"}
              </span>
              <span className="block truncate text-xs text-slate-400">
                {policy.policy_number} · {policy.insurer?.name ?? policy.product_line} ·{" "}
                {show(`₹${Number(policy.premium_gross).toLocaleString("en-IN")}`)}
              </span>
            </span>
            <WhatsAppButton
              phone={policy.customer?.mobile}
              message={waTemplates.renewal(
                policy.customer?.full_name ?? "",
                `${policy.policy_number} (expires ${formatDate(policy.expiry_date)})`
              )}
              label={`Message ${policy.customer?.full_name ?? "customer"} about renewal`}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
