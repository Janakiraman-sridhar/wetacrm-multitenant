import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Landmark, PieChart as PieIcon, Repeat, TrendingUp } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from "recharts";

import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { useValuePrivacy } from "@/lib/privacy";

const PIE_COLORS = ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#0EA5E9", "#8B5CF6", "#EC4899", "#64748B"];

/**
 * The reports an agency reviews, on the dashboard rather than behind a Reports tab.
 *
 * The deal-centric cards this replaces were not merely unhelpful to an insurance
 * workspace — they were wrong. "Revenue over time" reads *won deal value*, and an
 * agency's money is premium and commission, so it showed ₹0 for a book worth ₹90k.
 * Every panel here reads `/reports/insurance/*`, which has computed all of this
 * since the reports module landed and only ever surfaced it on a separate page.
 *
 * Each fetches its own data rather than being fed by the one dashboard payload, so
 * a card that is switched off costs nothing.
 */

function Panel({
  title, icon: Icon, tone = "text-primary-600", to, children,
}: {
  title: string;
  icon: any;
  tone?: string;
  to?: string;
  children: React.ReactNode;
}) {
  const navigate = useNavigate();
  return (
    <section className="card flex min-h-0 flex-col p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold">
          <Icon size={16} className={tone} />
          {title}
        </h2>
        {to && (
          <button
            className="btn-ghost !px-2 !py-1 text-xs text-slate-400 hover:text-primary-600"
            onClick={() => navigate(to)}
          >
            Open
          </button>
        )}
      </div>
      {children}
    </section>
  );
}

const monthLabel = (period: string) =>
  new Date(`${period}-01T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "2-digit" });

function useProduction(months = 12) {
  return useQuery({
    queryKey: ["insurance-production", months],
    queryFn: async () =>
      (await api.get("/reports/insurance/production", { params: { months } })).data,
    staleTime: 60_000,
  });
}

/** New against renewal premium, month by month — what "revenue over time" means here. */
export function PremiumWritten() {
  const { data, isLoading } = useProduction();
  const { hidden } = useValuePrivacy();
  const series = (data?.by_month ?? []).map((r: any) => ({ ...r, label: monthLabel(r.month) }));

  return (
    <Panel title="Premium written" icon={TrendingUp} to="/reports">
      {isLoading ? (
        <p className="py-16 text-center text-sm text-slate-400">Loading…</p>
      ) : series.length === 0 ? (
        <p className="py-16 text-center text-sm text-slate-400">No policies issued yet.</p>
      ) : (
        <>
          <p className="mb-2 text-sm text-slate-500 dark:text-slate-400">
            <span className="font-medium text-slate-900 dark:text-slate-100">
              {hidden ? "••••" : formatMoney(data.total_premium)}
            </span>{" "}
            across {data.total_policies} polic{data.total_policies === 1 ? "y" : "ies"}
          </p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={series}>
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
              <XAxis dataKey="label" fontSize={12} tickLine={false} interval="preserveStartEnd" />
              <YAxis fontSize={12} tickLine={false} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
              <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
              <Legend />
              {/* Split because an agency that cannot tell new business from renewal
                  cannot tell growth from retention. */}
              <Bar dataKey="new" stackId="p" fill="#4F46E5" name="New" radius={[0, 0, 0, 0]} />
              <Bar dataKey="renewal" stackId="p" fill="#10B981" name="Renewal" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}
    </Panel>
  );
}

/** Where the book sits. Replaces "open pipeline by stage" for a workspace with no deals. */
export function BookByInsurer() {
  const { data, isLoading } = useProduction();
  const rows = (data?.by_insurer ?? []).slice(0, 8);

  return (
    <Panel title="Book by insurer" icon={PieIcon} to="/reports">
      {isLoading ? (
        <p className="py-16 text-center text-sm text-slate-400">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="py-16 text-center text-sm text-slate-400">Nothing written yet.</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie data={rows} dataKey="premium" nameKey="name" cx="50%" cy="50%"
                 innerRadius={50} outerRadius={85} paddingAngle={2}>
              {rows.map((_: any, i: number) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
}

/** Earned against received, and the policies whose commission was never filled in. */
export function CommissionDue() {
  const navigate = useNavigate();
  const { show } = useValuePrivacy();
  const { data, isLoading } = useQuery({
    queryKey: ["insurance-commission"],
    queryFn: async () => (await api.get("/reports/insurance/commission")).data,
    staleTime: 60_000,
  });

  const missing = data?.policies_missing_commission ?? [];

  return (
    <Panel title="Commission" icon={Landmark} tone="text-emerald-600 dark:text-emerald-400" to="/reports">
      {isLoading ? (
        <p className="py-10 text-center text-sm text-slate-400">Loading…</p>
      ) : (
        <>
          <dl className="grid grid-cols-3 gap-2 text-center">
            {[
              ["Earned", data.total_earned],
              ["Received", data.loan_payout_received],
              ["Outstanding", data.loan_payout_outstanding],
            ].map(([label, value]: any) => (
              <div key={label} className="rounded-lg bg-slate-50 p-2 dark:bg-slate-800/50">
                <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
                <dd className="mt-0.5 text-sm font-semibold tabular-nums">
                  {show(formatMoney(value))}
                </dd>
              </div>
            ))}
          </dl>

          {/* The actionable half: a policy with a percentage and no amount is money
              the agency has not billed for. */}
          {missing.length > 0 && (
            <div className="mt-3 rounded-lg bg-amber-50 p-2.5 dark:bg-amber-950/30">
              <p className="flex items-center gap-1.5 text-xs font-medium text-amber-800 dark:text-amber-200">
                <AlertTriangle size={12} />
                {missing.length} polic{missing.length === 1 ? "y has" : "ies have"} no commission recorded
              </p>
              <ul className="mt-1.5 space-y-0.5">
                {missing.slice(0, 4).map((p: any) => (
                  <li key={p.policy_id}>
                    <button
                      className="text-xs text-amber-900 hover:underline dark:text-amber-100"
                      onClick={() => navigate("/policies")}
                    >
                      {p.policy_number} · {show(formatMoney(p.premium))} at {p.percent}%
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

/** The cheapest business in an agency: the customer already on the books. */
export function CrossSell() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["insurance-cross-sell"],
    queryFn: async () => (await api.get("/reports/insurance/cross-sell")).data,
    staleTime: 60_000,
  });

  const single = data?.single_line_customers ?? [];
  const none = data?.customers_with_no_policy ?? [];

  return (
    <Panel title="Cross-sell" icon={Repeat} tone="text-violet-600 dark:text-violet-400" to="/reports">
      {isLoading ? (
        <p className="py-10 text-center text-sm text-slate-400">Loading…</p>
      ) : single.length === 0 && none.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-400">
          Every customer holds a policy in each line.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {single.slice(0, 5).map((c: any) => (
            <li key={c.contact_id} className="flex items-center gap-2 text-sm">
              <span className="min-w-0 flex-1 truncate">{c.customer}</span>
              <span className="flex shrink-0 gap-1">
                {(c.missing ?? []).map((line: string) => (
                  <span
                    key={line}
                    className="badge bg-violet-50 text-[10px] capitalize text-violet-700 dark:bg-violet-900/40 dark:text-violet-300"
                    title={`Holds ${(c.holds ?? []).join(", ")} — no ${line} cover`}
                  >
                    no {line}
                  </span>
                ))}
              </span>
            </li>
          ))}
          {none.length > 0 && (
            <li className="pt-1 text-xs text-slate-500 dark:text-slate-400">
              <button className="hover:underline" onClick={() => navigate("/contacts")}>
                {none.length} customer{none.length === 1 ? "" : "s"} with no policy at all
              </button>
            </li>
          )}
        </ul>
      )}
    </Panel>
  );
}

/** Loan cases by lender, and what is still owed on the disbursed ones. */
export function LoanPayouts() {
  const { show } = useValuePrivacy();
  const { data, isLoading } = useQuery({
    queryKey: ["insurance-loan-payouts"],
    queryFn: async () => (await api.get("/reports/insurance/loan-payouts")).data,
    staleTime: 60_000,
  });

  const rows = (data?.by_lender ?? []).filter((r: any) => r.cases > 0);
  const outstanding = rows.reduce((sum: number, r: any) => sum + Number(r.outstanding || 0), 0);

  return (
    <Panel title="Loan payouts" icon={Landmark} tone="text-sky-600 dark:text-sky-400" to="/loans">
      {isLoading ? (
        <p className="py-10 text-center text-sm text-slate-400">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-400">No loan cases yet.</p>
      ) : (
        <>
          <p className="mb-2 text-sm text-slate-500 dark:text-slate-400">
            <span
              className={clsx(
                "font-medium",
                outstanding > 0 ? "text-amber-600 dark:text-amber-400" : "text-slate-900 dark:text-slate-100"
              )}
            >
              {show(formatMoney(outstanding))}
            </span>{" "}
            still to come in
          </p>
          <ul className="space-y-1.5">
            {rows.slice(0, 6).map((r: any) => (
              <li key={r.lender} className="flex items-center gap-2 text-sm">
                <span className="min-w-0 flex-1 truncate">{r.lender}</span>
                <span className="shrink-0 text-xs text-slate-400">
                  {r.cases} case{r.cases === 1 ? "" : "s"}
                </span>
                <span className="w-24 shrink-0 text-right tabular-nums">
                  {show(formatMoney(r.outstanding))}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}
