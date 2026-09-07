import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Eye, EyeOff } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { api } from "@/lib/api";
import { useValuePrivacy } from "@/lib/privacy";
import type { PolicyStats } from "@/types";

function inr(value: string | number): string {
  const amount = Number(value || 0);
  if (amount >= 10_000_000) return `₹${(amount / 10_000_000).toFixed(2)} Cr`;
  if (amount >= 100_000) return `₹${(amount / 100_000).toFixed(2)} L`;
  return `₹${amount.toLocaleString("en-IN")}`;
}

/**
 * The KPI strip an agent opens the day with.
 *
 * One eye icon hides every figure at once — useful when screen-sharing or sitting
 * with a customer. The preference is read synchronously on first render, so the
 * numbers never flash before it applies.
 *
 * Every tile is a link into the list it counts; a number you cannot drill into is
 * a number you cannot act on.
 */
export function InsuranceKpis() {
  const navigate = useNavigate();
  const { hidden, toggle, show } = useValuePrivacy();

  const { data, isLoading } = useQuery({
    queryKey: ["policy-stats"],
    queryFn: async () => (await api.get<PolicyStats>("/policies/stats")).data,
    staleTime: 60_000,
  });

  const tiles = [
    { label: "Customers", value: data?.customers ?? 0, to: "/contacts", tone: "slate" },
    { label: "Active policies", value: data?.active_policies ?? 0, to: "/policies?status=active", tone: "emerald" },
    { label: "Book premium", value: inr(data?.book_premium ?? 0), to: "/policies", tone: "primary" },
    {
      label: "Renewals in 60 days", value: data?.renewals_60d ?? 0,
      to: "/policies?expiring=60", tone: "amber",
      hint: `${data?.renewals_30d ?? 0} within 30 · ${data?.renewals_7d ?? 0} within 7`,
    },
    {
      label: "New business (MTD)", value: data?.new_business_mtd_count ?? 0,
      to: "/policies", tone: "slate", hint: inr(data?.new_business_mtd_premium ?? 0),
    },
    { label: "Lapsed", value: data?.lapsed ?? 0, to: "/policies?status=lapsed", tone: "red" },
    { label: "Commission (MTD)", value: inr(data?.commission_mtd ?? 0), to: "/reports", tone: "slate" },
    { label: "Birthdays this week", value: data?.birthdays_this_week ?? 0, to: "/contacts", tone: "primary" },
  ];

  const tones: Record<string, string> = {
    slate: "text-slate-900 dark:text-slate-100",
    primary: "text-primary-600 dark:text-primary-400",
    emerald: "text-emerald-600 dark:text-emerald-400",
    amber: "text-amber-600 dark:text-amber-400",
    red: "text-red-600 dark:text-red-400",
  };

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">Your book</h2>
        <button
          onClick={toggle}
          className="btn-ghost !px-2 !py-1 text-xs"
          title={hidden ? "Show figures" : "Hide every figure on this page"}
          aria-pressed={hidden}
        >
          {hidden ? <Eye size={14} /> : <EyeOff size={14} />}
          {hidden ? "Show values" : "Hide values"}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tiles.map((tile) => (
          <button
            key={tile.label}
            onClick={() => navigate(tile.to)}
            className="card p-4 text-left transition-shadow hover:shadow-md"
            title={`Open ${tile.label}`}
          >
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {tile.label}
            </p>
            <p
              className={clsx(
                "mt-1 text-2xl font-semibold tabular-nums",
                tones[tile.tone],
                hidden && "select-none blur-[6px]"
              )}
            >
              {isLoading ? "—" : show(tile.value)}
            </p>
            {tile.hint && (
              <p className={clsx("mt-0.5 text-xs text-slate-400", hidden && "select-none blur-[4px]")}>
                {show(tile.hint)}
              </p>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}
