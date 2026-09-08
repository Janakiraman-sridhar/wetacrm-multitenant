import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowUpRight, Cake, CalendarClock, Eye, EyeOff, Percent, ShieldCheck, ShieldOff,
  TrendingUp, Users, Wallet, type LucideIcon,
} from "lucide-react";
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

/** What a figure is telling the agent, which is what decides whether it gets colour. */
type Tone = "neutral" | "money" | "due" | "bad" | "good";

interface Tile {
  label: string;
  value: string | number;
  to: string;
  icon: LucideIcon;
  tone: Tone;
  /** Colour is worth spending only when the number is asking for something. */
  alert?: boolean;
  hint?: string;
}

const TONES: Record<Tone, string> = {
  neutral: "text-slate-900 dark:text-slate-100",
  money: "text-slate-900 dark:text-slate-100",
  due: "text-amber-600 dark:text-amber-400",
  bad: "text-red-600 dark:text-red-400",
  good: "text-primary-600 dark:text-primary-400",
};

const ICON_TONES: Record<Tone, string> = {
  neutral: "text-slate-400 dark:text-slate-500",
  money: "text-primary-500 dark:text-primary-400",
  due: "text-amber-500",
  bad: "text-red-500",
  good: "text-primary-500 dark:text-primary-400",
};

/**
 * The KPI strip an agent opens the day with.
 *
 * One eye icon hides every figure at once — useful when screen-sharing or sitting
 * with a customer. The preference is read synchronously on first render, so the
 * numbers never flash before it applies.
 *
 * Every tile is a link into the list it counts; a number you cannot drill into is
 * a number you cannot act on.
 *
 * **Colour is reserved for figures that want something done.** Painting "Lapsed 0"
 * red and "Renewals 0" amber turns two pieces of good news into warnings, and once
 * every tile is coloured none of them mean anything — the strip reads as decoration
 * and an agent stops scanning it. So a tone applies only when the number is non-zero
 * and actionable; everything else stays neutral, and the money figures are marked by
 * their icon rather than by shouting.
 */
export function InsuranceKpis() {
  const navigate = useNavigate();
  const { hidden, toggle, show } = useValuePrivacy();

  const { data, isLoading } = useQuery({
    queryKey: ["policy-stats"],
    queryFn: async () => (await api.get<PolicyStats>("/policies/stats")).data,
    staleTime: 60_000,
  });

  const renewals = data?.renewals_60d ?? 0;
  const lapsed = data?.lapsed ?? 0;
  const birthdays = data?.birthdays_this_week ?? 0;

  const tiles: Tile[] = [
    {
      label: "Customers", value: data?.customers ?? 0, to: "/contacts",
      icon: Users, tone: "neutral",
    },
    {
      label: "Active policies", value: data?.active_policies ?? 0,
      to: "/policies?status=active", icon: ShieldCheck, tone: "neutral",
    },
    {
      label: "Book premium", value: inr(data?.book_premium ?? 0), to: "/policies",
      icon: Wallet, tone: "money", hint: "Gross, in force",
    },
    {
      label: "Renewals in 60 days", value: renewals, to: "/policies?expiring=60",
      icon: CalendarClock, tone: "due", alert: renewals > 0,
      hint: `${data?.renewals_30d ?? 0} within 30 · ${data?.renewals_7d ?? 0} within 7`,
    },
    {
      label: "New business (MTD)", value: data?.new_business_mtd_count ?? 0,
      to: "/policies", icon: TrendingUp, tone: "neutral",
      hint: `${inr(data?.new_business_mtd_premium ?? 0)} premium`,
    },
    {
      label: "Lapsed", value: lapsed, to: "/policies?status=lapsed",
      icon: ShieldOff, tone: "bad", alert: lapsed > 0,
      hint: lapsed > 0 ? "Worth a call" : "Nothing lapsed",
    },
    {
      label: "Commission (MTD)", value: inr(data?.commission_mtd ?? 0), to: "/reports",
      icon: Percent, tone: "money", hint: "Earned this month",
    },
    {
      label: "Birthdays this week", value: birthdays, to: "/contacts",
      icon: Cake, tone: "good", alert: birthdays > 0,
      hint: birthdays > 0 ? "Send a wish" : "None this week",
    },
  ];

  return (
    <section>
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Your book</h2>
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

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map((tile) => {
          const tone: Tone = tile.alert === false ? "neutral" : tile.tone;
          const Icon = tile.icon;
          const secret = !!tile.hint && /\d/.test(tile.hint);
          const hint = tile.hint && (secret ? show(tile.hint) : tile.hint);
          return (
            <button
              key={tile.label}
              onClick={() => navigate(tile.to)}
              title={`Open ${tile.label}`}
              className={clsx(
                // A button vertically centres its own content, so a tile carrying a
                // hint sat 9px higher than the one beside it and the whole row read
                // as ragged. Laying it out as a column fixes the baselines for good.
                "card group relative flex flex-col items-start p-4 text-left",
                "transition-all hover:-translate-y-0.5 hover:border-primary-300 hover:shadow-md",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40",
                "dark:hover:border-primary-800"
              )}
            >
              <span className="flex w-full items-start justify-between gap-2">
                {/* Two lines are reserved on a phone, where the longer labels wrap
                    and would otherwise push their value below the one beside it. */}
                <span className="min-h-[2rem] text-[11px] font-semibold uppercase leading-4 tracking-wider text-slate-500 sm:min-h-0 dark:text-slate-400">
                  {tile.label}
                </span>
                <Icon
                  size={15}
                  className={clsx("mt-0.5 shrink-0 transition-colors", ICON_TONES[tone])}
                />
              </span>

              {isLoading ? (
                <span className="mt-2 h-7 w-20 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
              ) : (
                <span
                  className={clsx(
                    "mt-1 text-2xl font-semibold tabular-nums leading-8",
                    TONES[tone],
                    hidden && "select-none blur-[6px]"
                  )}
                >
                  {show(tile.value)}
                </span>
              )}

              {/* Pushed to the bottom so every hint in a row shares one line, and
                  tiles without one keep the same height. Only a hint carrying a
                  figure is masked — blanking "Nothing lapsed" hides nothing and
                  just looks broken. */}
              <span
                className={clsx(
                  "mt-auto min-h-[1rem] pt-1 text-xs text-slate-400 dark:text-slate-500",
                  hidden && secret && "select-none blur-[4px]"
                )}
              >
                {isLoading ? "" : hint}
              </span>

              <ArrowUpRight
                size={14}
                className="absolute bottom-3 right-3 text-primary-500 opacity-0 transition-opacity group-hover:opacity-100"
              />
            </button>
          );
        })}
      </div>
    </section>
  );
}
