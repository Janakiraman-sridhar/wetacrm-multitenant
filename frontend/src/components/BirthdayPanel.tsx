import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Cake, Gift } from "lucide-react";
import { useState } from "react";

import { WhatsAppButton } from "@/components/CustomerChip";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { waTemplates } from "@/lib/whatsapp";

interface Birthday {
  id: string;
  full_name: string;
  date_of_birth: string;
  turning: number;
  days_away: number;
  primary_phone: string | null;
  email: string | null;
}

const RANGES = [
  { label: "Today", days: 0 },
  { label: "This week", days: 7 },
  { label: "This month", days: 31 },
] as const;

/**
 * Whose birthday is coming up, with one click to wish them.
 *
 * Backed by an indexed MMDD column rather than a date function over every row, so
 * it stays a range scan as a book of business grows.
 */
export function BirthdayPanel({ compact = false }: { compact?: boolean }) {
  const { user } = useAuth();
  const [range, setRange] = useState<number>(7);

  const { data, isLoading } = useQuery({
    queryKey: ["birthdays", range],
    queryFn: async () =>
      (await api.get<Birthday[]>("/contacts/birthdays", { params: { within_days: range } })).data,
    staleTime: 5 * 60_000,
  });

  const agentName = `${user?.first_name ?? ""} ${user?.last_name ?? ""}`.trim();
  const rows = data ?? [];

  return (
    <section className="card flex min-h-0 flex-col p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold">
          <Cake size={16} className="text-primary-600 dark:text-primary-400" />
          Birthdays
        </h2>
        <div className="flex gap-1">
          {RANGES.map((option) => (
            <button
              key={option.label}
              onClick={() => setRange(option.days)}
              className={clsx(
                "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                range === option.days
                  ? "bg-primary-600 text-white"
                  : "text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <p className="py-6 text-center text-sm text-slate-400">Loading…</p>}

      {!isLoading && rows.length === 0 && (
        <p className="py-6 text-center text-sm text-slate-400">
          No birthdays in this period.
        </p>
      )}

      <ul className={clsx("min-h-0 space-y-1 overflow-y-auto", compact && "max-h-64")}>
        {rows.map((person) => (
          <li
            key={person.id}
            className="flex items-center gap-3 rounded-lg px-2 py-1.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
          >
            <span
              className={clsx(
                "grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-semibold",
                person.days_away === 0
                  ? "bg-primary-600 text-white"
                  : "bg-primary-50 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300"
              )}
              title={person.days_away === 0 ? "Today" : `In ${person.days_away} days`}
            >
              {person.days_away === 0 ? <Gift size={14} /> : `${person.days_away}d`}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{person.full_name}</span>
              <span className="block text-xs text-slate-400">
                Turning {person.turning}
                {person.primary_phone ? ` · ${person.primary_phone}` : ""}
              </span>
            </span>
            <WhatsAppButton
              phone={person.primary_phone}
              message={waTemplates.birthday(person.full_name, agentName)}
              label={`Send birthday wishes to ${person.full_name}`}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
