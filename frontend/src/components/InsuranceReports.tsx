import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Cake, CalendarClock, Download, Handshake, Landmark, Repeat, Trophy, TrendingUp, Wallet,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { PageSpinner } from "@/components/ui";
import { useToast } from "@/context/ToastContext";
import { API_URL, api, tokenStore } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useValuePrivacy } from "@/lib/privacy";
import { openWhatsApp, waTemplates } from "@/lib/whatsapp";

/**
 * The reports an insurance agency actually works from.
 *
 * Three of them — the renewal register, the lapsed list and the birthday list — are
 * call lists rather than dashboards, so they carry the phone number and a WhatsApp
 * button in the row. Nobody should have to open a customer record to make the call
 * the report just told them to make.
 */

const REPORTS = [
  { key: "renewals", label: "Renewal register", icon: CalendarClock, description: "What is expiring, with numbers to call", exports: true },
  { key: "production", label: "Production", icon: TrendingUp, description: "Premium written, new against renewal" },
  { key: "commission", label: "Commission & payouts", icon: Wallet, description: "Earned, received and outstanding" },
  { key: "retention", label: "Retention", icon: Repeat, description: "How much of the book renewed", exports: true },
  { key: "cross-sell", label: "Cross-sell", icon: Handshake, description: "Customers missing a product line", exports: true },
  { key: "leaderboard", label: "Agent leaderboard", icon: Trophy, description: "Who wrote what" },
  { key: "loan-payouts", label: "Loan payouts", icon: Landmark, description: "By lender, and what is still owed", exports: true },
  { key: "birthdays", label: "Birthdays", icon: Cake, description: "Who to wish, and when", exports: true },
] as const;

type ReportKey = (typeof REPORTS)[number]["key"];

/** Which `?months=`/`?within_days=` window each report reads. */
const WINDOWED: Record<string, "days" | "months" | null> = {
  renewals: "days",
  birthdays: "days",
  production: "months",
  commission: "months",
  retention: "months",
  leaderboard: "months",
  "cross-sell": null,
  "loan-payouts": null,
};

const DAY_CHOICES = [7, 15, 30, 60, 90];
const MONTH_CHOICES = [3, 6, 12, 24];

const inr = (value: unknown) => `₹${Math.round(Number(value || 0)).toLocaleString("en-IN")}`;

function monthLabel(m: string): string {
  return new Date(`${m}-01T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

function Kpi({ label, value, tone }: { label: string; value: string | number; tone?: "good" | "bad" }) {
  return (
    <div className="card px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</p>
      <p
        className={clsx(
          "mt-0.5 truncate text-lg font-bold",
          tone === "good" && "text-emerald-600 dark:text-emerald-400",
          tone === "bad" && "text-red-600 dark:text-red-400"
        )}
      >
        {value}
      </p>
    </div>
  );
}

function Section({ title, children, wide = false }: { title: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className={clsx("card p-4", wide && "xl:col-span-2")}>
      <h2 className="mb-3 font-semibold">{title}</h2>
      {children}
    </div>
  );
}

/** A scrollable table; `call` turns a row into a WhatsApp click-to-chat. */
function Table({
  columns,
  rows,
  call,
  empty = "Nothing to show.",
}: {
  columns: { key: string; label: string; align?: "right"; render?: (row: any) => React.ReactNode }[];
  rows: any[];
  call?: (row: any) => { phone?: string | null; message: string };
  empty?: string;
}) {
  if (!rows.length) return <p className="py-8 text-center text-sm text-slate-400">{empty}</p>;
  return (
    <div className="max-h-[26rem] overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-white dark:bg-slate-900">
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800">
            {columns.map((c) => (
              <th key={c.key} className={clsx("px-2 py-2 font-semibold", c.align === "right" && "text-right")}>
                {c.label}
              </th>
            ))}
            {call && <th className="px-2 py-2" />}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.policy_id ?? row.contact_id ?? row.loan_id ?? i} className="border-b border-slate-100 dark:border-slate-800/60">
              {columns.map((c) => (
                <td key={c.key} className={clsx("px-2 py-2", c.align === "right" && "text-right tabular-nums")}>
                  {c.render ? c.render(row) : row[c.key] ?? "—"}
                </td>
              ))}
              {call && (
                <td className="px-2 py-2 text-right">
                  {(() => {
                    const target = call(row);
                    return target.phone ? (
                      <button
                        className="btn-ghost !px-2 !py-1 text-xs text-emerald-600"
                        onClick={() => openWhatsApp(target.phone, target.message)}
                        title={`WhatsApp ${target.phone}`}
                      >
                        WhatsApp
                      </button>
                    ) : (
                      <span className="text-xs text-slate-300">no number</span>
                    );
                  })()}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function InsuranceReports() {
  const [report, setReport] = useState<ReportKey>("renewals");
  const [days, setDays] = useState(60);
  const [months, setMonths] = useState(12);
  const { show } = useValuePrivacy();
  const { toast } = useToast();

  const window = WINDOWED[report];
  const params = window === "days" ? { within_days: days } : window === "months" ? { months } : {};

  const { data, isLoading } = useQuery({
    queryKey: ["insurance-report", report, params],
    queryFn: async () => (await api.get(`/reports/insurance/${report}`, { params })).data,
  });

  const active = REPORTS.find((r) => r.key === report)!;

  async function exportCsv() {
    try {
      const query = new URLSearchParams(
        Object.entries(params).map(([k, v]) => [k, String(v)])
      ).toString();
      const res = await fetch(
        `${API_URL}/api/v1/reports/insurance/${report}/export?${query}`,
        { headers: { Authorization: `Bearer ${tokenStore.access}` } }
      );
      if (!res.ok) throw new Error("export failed");
      const blob = await res.blob();
      const match = (res.headers.get("Content-Disposition") || "").match(/filename="?([^"]+)"?/);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = match?.[1] || `${report}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast("Could not download that report", "error");
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-400">{active.description}.</p>
        <div className="flex items-center gap-2">
          {window === "days" && (
            <select className="input !w-auto !py-1.5 text-sm" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {DAY_CHOICES.map((d) => (
                <option key={d} value={d}>
                  Next {d} days
                </option>
              ))}
            </select>
          )}
          {window === "months" && (
            <select className="input !w-auto !py-1.5 text-sm" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
              {MONTH_CHOICES.map((m) => (
                <option key={m} value={m}>
                  Last {m} months
                </option>
              ))}
            </select>
          )}
          {"exports" in active && active.exports && (
            <button className="btn-secondary text-sm" onClick={exportCsv}>
              <Download size={15} /> Export CSV
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
        {REPORTS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setReport(key)}
            className={clsx(
              "card flex flex-col items-start gap-2 p-3 text-left transition-all",
              report === key
                ? "border-primary-400 ring-2 ring-primary-500/30 dark:border-primary-600"
                : "hover:border-slate-300 hover:shadow-md dark:hover:border-slate-600"
            )}
          >
            <span
              className={clsx(
                "flex h-8 w-8 items-center justify-center rounded-lg",
                report === key
                  ? "bg-primary-600 text-white"
                  : "bg-primary-50 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300"
              )}
            >
              <Icon size={16} />
            </span>
            <span className="text-xs font-semibold leading-tight">{label}</span>
          </button>
        ))}
      </div>

      {isLoading || !data ? <PageSpinner /> : <Report report={report} data={data} show={show} />}
    </div>
  );
}

function Report({
  report,
  data,
  show,
}: {
  report: ReportKey;
  data: any;
  show: (v: string | number | null | undefined) => string | number;
}) {
  // Memoised so the chart is not handed a fresh array on every render — recharts
  // treats that as new data and restarts its animation.
  const byMonth = useMemo(
    () => (data?.by_month ?? []).map((r: any) => ({ ...r, label: monthLabel(r.month) })),
    [data]
  );

  if (report === "renewals") {
    const due7 = data.filter((r: any) => r.days_to_expiry <= 7).length;
    const due30 = data.filter((r: any) => r.days_to_expiry <= 30).length;
    const premium = data.reduce((sum: number, r: any) => sum + Number(r.premium || 0), 0);
    return (
      <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi label="Policies due" value={data.length} />
          <Kpi label="Within 30 days" value={due30} />
          <Kpi label="Within 7 days" value={due7} tone={due7 ? "bad" : undefined} />
          <Kpi label="Premium at risk" value={show(inr(premium))} />
        </div>
        <Section title="Call list">
          <Table
            rows={data}
            call={(row) => ({
              phone: row.mobile,
              message: waTemplates.renewal(row.customer, `${row.policy_number} (${row.insurer})`),
            })}
            columns={[
              { key: "customer", label: "Customer" },
              { key: "policy_number", label: "Policy" },
              { key: "insurer", label: "Insurer" },
              { key: "product_line", label: "Line", render: (r) => <span className="badge">{r.product_line}</span> },
              { key: "expiry_date", label: "Expires", render: (r) => formatDate(r.expiry_date) },
              {
                key: "days_to_expiry", label: "Days", align: "right",
                render: (r) => (
                  <span className={clsx(r.days_to_expiry <= 7 && "font-semibold text-red-600")}>
                    {r.days_to_expiry}
                  </span>
                ),
              },
              { key: "premium", label: "Premium", align: "right", render: (r) => show(inr(r.premium)) },
              { key: "agent", label: "Agent" },
            ]}
            empty="Nothing expiring in this window."
          />
        </Section>
      </>
    );
  }

  if (report === "production") {
    return (
      <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <Kpi label="Policies written" value={data.total_policies} />
          <Kpi label="Premium" value={show(inr(data.total_premium))} />
          <Kpi label="Commission" value={show(inr(data.total_commission))} />
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <Section title="New vs renewal premium" wide>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={byMonth} barCategoryGap="25%">
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" strokeOpacity={0.4} />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} width={70} />
                <Tooltip formatter={(v: any) => inr(v)} />
                <Legend />
                {/* `barSize` because a workspace's first month is a single category,
                    and `isAnimationActive={false}` because the grow-in animation
                    restarts on every re-render and can freeze the bars at a sliver
                    of their height — a report that silently understates itself is
                    worse than one with no animation. */}
                <Bar dataKey="new" stackId="p" fill="#4F46E5" name="New" barSize={48} isAnimationActive={false} />
                <Bar dataKey="renewal" stackId="p" fill="#10B981" name="Renewal" barSize={48} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </Section>
          <Section title="By insurer">
            <Table
              rows={data.by_insurer}
              columns={[
                { key: "name", label: "Insurer" },
                { key: "count", label: "Policies", align: "right" },
                { key: "premium", label: "Premium", align: "right", render: (r) => show(inr(r.premium)) },
              ]}
            />
          </Section>
          <Section title="By product line">
            <Table
              rows={data.by_product_line}
              columns={[
                { key: "name", label: "Line" },
                { key: "count", label: "Policies", align: "right" },
                { key: "premium", label: "Premium", align: "right", render: (r) => show(inr(r.premium)) },
              ]}
            />
          </Section>
          <Section title="By bank / source">
            <Table
              rows={data.by_bank}
              columns={[
                { key: "name", label: "Bank" },
                { key: "count", label: "Policies", align: "right" },
                { key: "premium", label: "Premium", align: "right", render: (r) => show(inr(r.premium)) },
              ]}
            />
          </Section>
          <Section title="By agent">
            <Table
              rows={data.by_agent}
              columns={[
                { key: "name", label: "Agent" },
                { key: "count", label: "Policies", align: "right" },
                { key: "premium", label: "Premium", align: "right", render: (r) => show(inr(r.premium)) },
              ]}
            />
          </Section>
        </div>
      </>
    );
  }

  if (report === "commission") {
    return (
      <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Kpi label="Policy commission" value={show(inr(data.policy_commission))} />
          <Kpi label="Loan payout expected" value={show(inr(data.loan_payout_expected))} />
          <Kpi label="Loan payout received" value={show(inr(data.loan_payout_received))} tone="good" />
          <Kpi
            label="Outstanding"
            value={show(inr(data.loan_payout_outstanding))}
            tone={Number(data.loan_payout_outstanding) > 0 ? "bad" : undefined}
          />
          <Kpi label="Total earned" value={show(inr(data.total_earned))} />
        </div>
        <Section title="Policies with a commission rate but no amount booked">
          <p className="mb-2 text-xs text-slate-400">
            Counted as unbilled, not as zero — a policy earning nothing and a policy nobody
            has invoiced for are different problems.
          </p>
          <Table
            rows={data.policies_missing_commission}
            columns={[
              { key: "policy_number", label: "Policy" },
              { key: "premium", label: "Premium", align: "right", render: (r) => show(inr(r.premium)) },
              { key: "percent", label: "Rate", align: "right", render: (r) => `${r.percent}%` },
              {
                key: "due", label: "Would earn", align: "right",
                render: (r) => show(inr((Number(r.premium) * Number(r.percent)) / 100)),
              },
            ]}
            empty="Every policy with a rate has an amount booked."
          />
        </Section>
      </>
    );
  }

  if (report === "retention") {
    return (
      <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Kpi label="Came up for renewal" value={data.due} />
          <Kpi label="Renewed" value={data.renewed} tone="good" />
          <Kpi label="Lapsed" value={data.lapsed} tone={data.lapsed ? "bad" : undefined} />
          <Kpi
            label="Retention rate"
            value={data.retention_rate === null ? "—" : `${data.retention_rate}%`}
          />
          <Kpi label="Premium lost" value={show(inr(data.premium_lost))} tone={data.premium_lost ? "bad" : undefined} />
        </div>
        <Section title="Lapsed policies — win-back list">
          <Table
            rows={data.lapsed_policies}
            call={(row) => ({
              phone: row.mobile,
              message: waTemplates.renewal(row.customer, row.policy_number),
            })}
            columns={[
              { key: "customer", label: "Customer" },
              { key: "policy_number", label: "Policy" },
              { key: "expired_on", label: "Expired", render: (r) => formatDate(r.expired_on) },
              { key: "premium", label: "Premium", align: "right", render: (r) => show(inr(r.premium)) },
            ]}
            empty="Nothing lapsed in this period."
          />
        </Section>
      </>
    );
  }

  if (report === "cross-sell") {
    return (
      <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-2">
          <Kpi label="Customers with a gap" value={data.counts.with_gaps} />
          <Kpi label="Customers with no policy" value={data.counts.with_no_policy} />
        </div>
        <Section title="Holding one line, missing another">
          <Table
            rows={data.single_line_customers}
            call={(row) => ({ phone: row.mobile, message: waTemplates.followUp(row.customer) })}
            columns={[
              { key: "customer", label: "Customer" },
              {
                key: "holds", label: "Holds",
                render: (r) => r.holds.map((l: string) => <span key={l} className="badge mr-1">{l}</span>),
              },
              {
                key: "missing", label: "Missing",
                render: (r) =>
                  r.missing.map((l: string) => (
                    <span key={l} className="badge mr-1 bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                      {l}
                    </span>
                  )),
              },
            ]}
            empty="Every customer holds a full spread."
          />
        </Section>
        <Section title="Customers with no policy at all">
          <Table
            rows={data.customers_with_no_policy}
            call={(row) => ({ phone: row.mobile, message: waTemplates.followUp(row.customer) })}
            columns={[{ key: "customer", label: "Customer" }, { key: "mobile", label: "Mobile" }]}
            empty="Everyone on the book holds a policy."
          />
        </Section>
      </>
    );
  }

  if (report === "leaderboard") {
    return (
      <Section title="Ranked on premium written">
        <Table
          rows={data}
          columns={[
            { key: "agent", label: "Agent" },
            { key: "policies", label: "Policies", align: "right" },
            { key: "premium", label: "Premium", align: "right", render: (r) => show(inr(r.premium)) },
            { key: "commission", label: "Commission", align: "right", render: (r) => show(inr(r.commission)) },
            { key: "loans", label: "Loans", align: "right" },
            { key: "loan_payout", label: "Loan payout", align: "right", render: (r) => show(inr(r.loan_payout)) },
          ]}
          empty="Nothing written in this period."
        />
      </Section>
    );
  }

  if (report === "loan-payouts") {
    const outstanding = data.by_lender.reduce((s: number, r: any) => s + Number(r.outstanding || 0), 0);
    return (
      <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <Kpi label="Lenders" value={data.by_lender.length} />
          <Kpi label="Cases awaiting payout" value={data.awaiting_payout.length} />
          <Kpi label="Outstanding" value={show(inr(outstanding))} tone={outstanding > 0 ? "bad" : undefined} />
        </div>
        <Section title="By lender">
          <Table
            rows={data.by_lender}
            columns={[
              { key: "lender", label: "Lender" },
              { key: "cases", label: "Cases", align: "right" },
              { key: "sanctioned", label: "Sanctioned", align: "right", render: (r) => show(inr(r.sanctioned)) },
              { key: "expected", label: "Expected", align: "right", render: (r) => show(inr(r.expected)) },
              { key: "received", label: "Received", align: "right", render: (r) => show(inr(r.received)) },
              { key: "outstanding", label: "Outstanding", align: "right", render: (r) => show(inr(r.outstanding)) },
            ]}
          />
        </Section>
        <Section title="Disbursed, payout still owed">
          <Table
            rows={data.awaiting_payout}
            columns={[
              { key: "customer", label: "Customer" },
              { key: "loan_type", label: "Loan" },
              { key: "lender", label: "Lender" },
              { key: "disbursed_on", label: "Disbursed", render: (r) => formatDate(r.disbursed_on) },
              { key: "expected", label: "Expected", align: "right", render: (r) => show(inr(r.expected)) },
              { key: "outstanding", label: "Outstanding", align: "right", render: (r) => show(inr(r.outstanding)) },
            ]}
            empty="Every disbursed case has been paid."
          />
        </Section>
      </>
    );
  }

  // birthdays
  return (
    <Section title="Upcoming birthdays">
      <Table
        rows={data}
        call={(row) => ({ phone: row.mobile, message: waTemplates.birthday(row.customer, "") })}
        columns={[
          { key: "customer", label: "Customer" },
          { key: "date_of_birth", label: "Date of birth", render: (r) => formatDate(r.date_of_birth) },
          { key: "turning", label: "Turning", align: "right" },
          {
            key: "days_away", label: "In", align: "right",
            render: (r) => (r.days_away === 0 ? <span className="font-semibold text-primary-600">today</span> : `${r.days_away}d`),
          },
          { key: "mobile", label: "Mobile" },
        ]}
        empty="No birthdays in this window."
      />
    </Section>
  );
}

/** Customer growth, shown under whichever report is open — it is context, not a report. */
export function CustomerGrowth() {
  const { data } = useQuery({
    queryKey: ["insurance-report", "customer-growth"],
    queryFn: async () => (await api.get("/reports/insurance/customer-growth")).data,
    staleTime: 5 * 60_000,
  });
  const rows = useMemo(
    () => (data ?? []).map((r: any) => ({ ...r, label: monthLabel(r.month) })),
    [data]
  );
  if (!data?.length) return null;
  return (
    <Section title="Customer growth">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" strokeOpacity={0.4} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="total" stroke="#4F46E5" name="Total customers" strokeWidth={2} isAnimationActive={false} />
          <Line type="monotone" dataKey="added" stroke="#10B981" name="Added" strokeWidth={2} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </Section>
  );
}
