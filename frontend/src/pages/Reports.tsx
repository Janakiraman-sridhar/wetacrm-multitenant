import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { IndianRupee, Kanban, Table2, Target, TrendingUp, Users } from "lucide-react";
import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { DateRangePicker, PresetKey, presetRange } from "@/components/DateRangePicker";
import { DrilldownModal, DrilldownTarget } from "@/components/DrilldownModal";
import { PageSpinner, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";

const PIE_COLORS = ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#0EA5E9", "#8B5CF6", "#EC4899", "#64748B"];

const TEMPLATES = [
  {
    key: "sales_performance",
    label: "Sales Performance",
    icon: TrendingUp,
    description: "Revenue, win rate and closed business",
  },
  {
    key: "pipeline_health",
    label: "Pipeline Health",
    icon: Kanban,
    description: "Open value, weighted forecast, top deals",
  },
  {
    key: "lead_generation",
    label: "Lead Generation",
    icon: Target,
    description: "Lead volume, sources and conversion",
  },
  {
    key: "team_performance",
    label: "Team Performance",
    icon: Users,
    description: "Won revenue and workload per member",
  },
  {
    key: "revenue_collections",
    label: "Revenue & Collections",
    icon: IndianRupee,
    description: "Invoiced, collected and outstanding",
  },
] as const;

type TemplateKey = (typeof TEMPLATES)[number]["key"];

function periodLabel(period: string, granularity: string): string {
  const d = new Date(granularity === "month" ? `${period}-01T00:00:00` : `${period}T00:00:00`);
  return granularity === "month"
    ? d.toLocaleDateString(undefined, { month: "short", year: "2-digit" })
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function monthLabel(m: string): string {
  return new Date(`${m}-01T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

function Kpi({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-0.5 truncate text-lg font-bold">{value}</p>
    </div>
  );
}

function Section({
  title,
  onData,
  children,
  wide = false,
}: {
  title: string;
  onData?: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={clsx("card p-4", wide && "xl:col-span-2")}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold">{title}</h2>
        {onData && (
          <button
            className="btn-ghost !px-2 !py-1 text-xs text-slate-400 hover:text-primary-600"
            onClick={onData}
            title="View & export the underlying data"
          >
            <Table2 size={14} /> Data
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

export default function Reports() {
  const [template, setTemplate] = useState<TemplateKey>("sales_performance");
  const [preset, setPreset] = useState<PresetKey>("12m");
  const [range, setRange] = useState(() => presetRange("12m"));
  const [drilldown, setDrilldown] = useState<DrilldownTarget | null>(null);
  const { start, end } = range;

  const { data, isLoading } = useQuery({
    queryKey: ["report-template", template, start, end],
    queryFn: async () => (await api.get(`/reports/templates/${template}`, { params: { start, end } })).data,
  });

  const open = (metric: string, label: string) => setDrilldown({ metric, label });
  const active = TEMPLATES.find((t) => t.key === template)!;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Reports</h1>
          <p className="text-sm text-slate-400">
            Predefined executive reports over your sales data. Every chart has its underlying records one click away.
          </p>
        </div>
        <DateRangePicker
          preset={preset}
          start={start}
          end={end}
          onChange={(p, s, e) => {
            setPreset(p);
            setRange({ start: s, end: e });
          }}
        />
      </div>

      {/* Template picker */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {TEMPLATES.map(({ key, label, icon: Icon, description }) => (
          <button
            key={key}
            onClick={() => setTemplate(key)}
            className={clsx(
              "card flex items-start gap-3 p-3.5 text-left transition-all",
              template === key
                ? "border-primary-400 ring-2 ring-primary-500/30 dark:border-primary-600"
                : "hover:border-slate-300 hover:shadow-md dark:hover:border-slate-600"
            )}
          >
            <span
              className={clsx(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                template === key
                  ? "bg-primary-600 text-white"
                  : "bg-primary-50 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300"
              )}
            >
              <Icon size={17} />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold leading-tight">{label}</span>
              <span className="mt-0.5 block text-xs leading-snug text-slate-400">{description}</span>
            </span>
          </button>
        ))}
      </div>

      {isLoading || !data ? (
        <PageSpinner />
      ) : (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {template === "sales_performance" && (
              <>
                <Kpi label="Revenue (won)" value={formatMoney(data.kpis.revenue)} />
                <Kpi label="Deals won" value={data.kpis.won_deals} />
                <Kpi label="Deals lost" value={data.kpis.lost_deals} />
                <Kpi label="Win rate" value={`${data.kpis.win_rate}%`} />
                <Kpi label="Avg deal size" value={formatMoney(data.kpis.avg_deal_size)} />
                <Kpi label="Open pipeline" value={formatMoney(data.kpis.open_pipeline_value)} />
              </>
            )}
            {template === "pipeline_health" && (
              <>
                <Kpi label="Open deals" value={data.kpis.open_deals} />
                <Kpi label="Open value" value={formatMoney(data.kpis.open_value)} />
                <Kpi label="Weighted forecast" value={formatMoney(data.kpis.weighted_forecast)} />
                <Kpi label="Avg probability" value={`${data.kpis.avg_probability}%`} />
                <Kpi label="Missing close date" value={data.kpis.no_close_date} />
              </>
            )}
            {template === "lead_generation" && (
              <>
                <Kpi label="Leads created" value={data.kpis.leads_created} />
                <Kpi label="Converted" value={data.kpis.converted} />
                <Kpi label="Conversion rate" value={`${data.kpis.conversion_rate}%`} />
                <Kpi label="Avg score" value={data.kpis.avg_score} />
                <Kpi label="Unassigned" value={data.kpis.unassigned} />
              </>
            )}
            {template === "team_performance" && (
              <>
                <Kpi label="Active members" value={data.kpis.active_members} />
                <Kpi label="Total won value" value={formatMoney(data.kpis.total_won_value)} />
                <Kpi label="Total won deals" value={data.kpis.total_won_deals} />
                <Kpi label="Best performer" value={data.kpis.best_performer} />
              </>
            )}
            {template === "revenue_collections" && (
              <>
                <Kpi label="Invoiced" value={formatMoney(data.kpis.invoiced_total)} />
                <Kpi label="Collected" value={formatMoney(data.kpis.collected_total)} />
                <Kpi label="Outstanding" value={formatMoney(data.kpis.outstanding)} />
                <Kpi label="Overdue invoices" value={data.kpis.overdue_invoices} />
                <Kpi label="Quotations issued" value={data.kpis.quotations_issued} />
                <Kpi label="Quote acceptance" value={`${data.kpis.quote_acceptance_rate}%`} />
              </>
            )}
          </div>

          {/* Sections */}
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {template === "sales_performance" && (
              <>
                <Section title="Revenue Over Time" onData={() => open("revenue_series", "Revenue — won deals")}>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={data.revenue_series.map((r: any) => ({ ...r, label: periodLabel(r.period, data.granularity) }))}>
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis dataKey="label" fontSize={12} tickLine={false} interval="preserveStartEnd" />
                      <YAxis fontSize={12} tickLine={false} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
                      <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
                      <Bar dataKey="revenue" fill="#4F46E5" radius={[4, 4, 0, 0]} name="Revenue" />
                    </BarChart>
                  </ResponsiveContainer>
                </Section>
                <Section title="Open Pipeline by Stage" onData={() => open("pipeline_by_stage", "Open deals by stage")}>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={data.pipeline_by_stage} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis type="number" fontSize={12} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
                      <YAxis type="category" dataKey="stage" fontSize={12} width={92} />
                      <Tooltip formatter={(v: any, name: any) => (name === "Value" ? formatMoney(Number(v)) : v)} />
                      <Legend />
                      <Bar dataKey="value" fill="#4F46E5" radius={[0, 4, 4, 0]} name="Value" />
                      <Bar dataKey="count" fill="#0EA5E9" radius={[0, 4, 4, 0]} name="Deals" />
                    </BarChart>
                  </ResponsiveContainer>
                </Section>
                <Section title="Top Performers" onData={() => open("team_performance", "Deals by owner")} wide>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data.top_performers}>
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis dataKey="name" fontSize={12} tickLine={false} />
                      <YAxis fontSize={12} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
                      <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
                      <Bar dataKey="won_value" fill="#10B981" radius={[4, 4, 0, 0]} name="Won value" />
                    </BarChart>
                  </ResponsiveContainer>
                </Section>
              </>
            )}

            {template === "pipeline_health" && (
              <>
                <Section title="Value vs Weighted Forecast by Stage" onData={() => open("pipeline_by_stage", "Open deals by stage")}>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={data.pipeline_by_stage} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis type="number" fontSize={12} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
                      <YAxis type="category" dataKey="stage" fontSize={12} width={92} />
                      <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
                      <Legend />
                      <Bar dataKey="value" fill="#4F46E5" radius={[0, 4, 4, 0]} name="Total value" />
                      <Bar dataKey="weighted" fill="#F59E0B" radius={[0, 4, 4, 0]} name="Weighted" />
                    </BarChart>
                  </ResponsiveContainer>
                </Section>
                <Section title="Expected Closes by Month" onData={() => open("open_deals", "Open deals")}>
                  {data.expected_closes.length === 0 ? (
                    <p className="py-16 text-center text-sm text-slate-400">No open deals with close dates.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height={240}>
                      <BarChart data={data.expected_closes.map((r: any) => ({ ...r, label: monthLabel(r.month) }))}>
                        <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                        <XAxis dataKey="label" fontSize={12} tickLine={false} />
                        <YAxis fontSize={12} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
                        <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
                        <Bar dataKey="value" fill="#0EA5E9" radius={[4, 4, 0, 0]} name="Expected value" />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </Section>
                <Section title="Top 10 Open Deals" onData={() => open("open_deals", "Open deals")} wide>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[640px] text-sm">
                      <thead>
                        <tr>
                          <th className="th">Deal</th>
                          <th className="th">Company</th>
                          <th className="th">Stage</th>
                          <th className="th !text-right">Value</th>
                          <th className="th !text-right">Prob.</th>
                          <th className="th">Owner</th>
                          <th className="th">Expected close</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.top_open_deals.map((d: any, i: number) => (
                          <tr key={i} className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-800">
                            <td className="td font-medium">{d.title}</td>
                            <td className="td">{d.company || "—"}</td>
                            <td className="td">
                              <StatusBadge value={d.stage.toLowerCase()} />
                            </td>
                            <td className="td text-right font-semibold">{formatMoney(d.value)}</td>
                            <td className="td text-right">{d.probability}%</td>
                            <td className="td">{d.owner || "—"}</td>
                            <td className="td">{d.expected_close_date || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Section>
              </>
            )}

            {template === "lead_generation" && (
              <>
                <Section title="Leads Created vs Converted" onData={() => open("lead_conversion", "Leads created in period")}>
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={data.lead_series.map((r: any) => ({ ...r, label: periodLabel(r.period, data.granularity) }))}>
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis dataKey="label" fontSize={12} tickLine={false} interval="preserveStartEnd" />
                      <YAxis fontSize={12} allowDecimals={false} />
                      <Tooltip />
                      <Legend />
                      <Line type="monotone" dataKey="created" stroke="#64748B" strokeWidth={2} dot={false} name="Created" />
                      <Line type="monotone" dataKey="converted" stroke="#10B981" strokeWidth={2} dot={false} name="Converted" />
                    </LineChart>
                  </ResponsiveContainer>
                </Section>
                <Section title="Lead Sources" onData={() => open("lead_sources", "Leads by source")}>
                  {data.lead_sources.length === 0 ? (
                    <p className="py-16 text-center text-sm text-slate-400">No leads in this period.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height={240}>
                      <PieChart>
                        <Pie data={data.lead_sources} dataKey="count" nameKey="source" cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={2}>
                          {data.lead_sources.map((_: any, i: number) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip />
                        <Legend />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </Section>
                <Section title="Status Breakdown" onData={() => open("lead_conversion", "Leads created in period")} wide>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data.status_breakdown}>
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis dataKey="status" fontSize={12} tickLine={false} className="capitalize" />
                      <YAxis fontSize={12} allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="count" fill="#8B5CF6" radius={[4, 4, 0, 0]} name="Leads" />
                    </BarChart>
                  </ResponsiveContainer>
                </Section>
              </>
            )}

            {template === "team_performance" && (
              <>
                <Section title="Won Value by Member" onData={() => open("team_performance", "Deals by owner")}>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={data.members}>
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis dataKey="name" fontSize={12} tickLine={false} />
                      <YAxis fontSize={12} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
                      <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
                      <Bar dataKey="won_value" fill="#4F46E5" radius={[4, 4, 0, 0]} name="Won value" />
                    </BarChart>
                  </ResponsiveContainer>
                </Section>
                <Section title="Member Scorecard" onData={() => open("team_performance", "Deals by owner")}>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[520px] text-sm">
                      <thead>
                        <tr>
                          <th className="th">Member</th>
                          <th className="th !text-right">Won value</th>
                          <th className="th !text-right">Won</th>
                          <th className="th !text-right">Lost</th>
                          <th className="th !text-right">Win rate</th>
                          <th className="th !text-right">Open</th>
                          <th className="th !text-right">Open value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.members.map((m: any, i: number) => (
                          <tr key={i} className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-800">
                            <td className="td font-medium">{m.name}</td>
                            <td className="td text-right font-semibold text-emerald-600 dark:text-emerald-400">{formatMoney(m.won_value)}</td>
                            <td className="td text-right">{m.won_count}</td>
                            <td className="td text-right">{m.lost_count}</td>
                            <td className="td text-right">{m.win_rate}%</td>
                            <td className="td text-right">{m.open_count}</td>
                            <td className="td text-right">{formatMoney(m.open_value)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {data.members.length === 0 && <p className="py-10 text-center text-sm text-slate-400">No owned deals in this period.</p>}
                  </div>
                </Section>
              </>
            )}

            {template === "revenue_collections" && (
              <>
                <Section title="Invoiced Over Time" onData={() => open("invoices", "Invoices in period")}>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={data.invoiced_series.map((r: any) => ({ ...r, label: periodLabel(r.period, data.granularity) }))}>
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis dataKey="label" fontSize={12} tickLine={false} interval="preserveStartEnd" />
                      <YAxis fontSize={12} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
                      <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
                      <Bar dataKey="value" fill="#4F46E5" radius={[4, 4, 0, 0]} name="Invoiced" />
                    </BarChart>
                  </ResponsiveContainer>
                </Section>
                <Section title="Invoices by Status" onData={() => open("invoices", "Invoices in period")}>
                  {data.invoices_by_status.length === 0 ? (
                    <p className="py-16 text-center text-sm text-slate-400">No invoices in this period.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height={240}>
                      <PieChart>
                        <Pie data={data.invoices_by_status} dataKey="value" nameKey="status" cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={2}>
                          {data.invoices_by_status.map((_: any, i: number) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
                        <Legend />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </Section>
                <Section title="Quotations by Status" onData={() => open("quotations", "Quotations in period")} wide>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data.quotes_by_status}>
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
                      <XAxis dataKey="status" fontSize={12} tickLine={false} className="capitalize" />
                      <YAxis fontSize={12} allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="count" fill="#10B981" radius={[4, 4, 0, 0]} name="Quotations" />
                    </BarChart>
                  </ResponsiveContainer>
                </Section>
              </>
            )}
          </div>

          <p className="text-xs text-slate-400">
            {active.label} · {start} → {end} · click "Data" on any section to inspect and export the records behind it.
          </p>
        </>
      )}

      <DrilldownModal target={drilldown} start={start} end={end} onClose={() => setDrilldown(null)} />
    </div>
  );
}
