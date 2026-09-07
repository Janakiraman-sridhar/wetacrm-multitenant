import { useQuery } from "@tanstack/react-query";
import {
  Briefcase, CalendarClock, CalendarDays, CheckSquare, IndianRupee, Table2, Target, Trophy,
} from "lucide-react";
import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { DateRangePicker, PresetKey, presetRange } from "@/components/DateRangePicker";
import { DrilldownModal, DrilldownTarget } from "@/components/DrilldownModal";
import { Avatar, PageSpinner } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, formatMoney, timeAgo } from "@/lib/format";
import { BirthdayPanel } from "@/components/BirthdayPanel";

const PIE_COLORS = ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#0EA5E9", "#8B5CF6", "#EC4899", "#64748B"];

function periodLabel(period: string, granularity: string): string {
  const d = new Date(granularity === "month" ? `${period}-01T00:00:00` : `${period}T00:00:00`);
  return granularity === "month"
    ? d.toLocaleDateString(undefined, { month: "short", year: "2-digit" })
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

// --- building blocks ------------------------------------------------------

function KpiCard({
  label, value, sub, icon: Icon, tone, onClick,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: any;
  tone: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title="Click to view the underlying records"
      className="card flex w-full items-center gap-4 p-4 text-left transition-shadow hover:shadow-md focus:outline-none focus:ring-2 focus:ring-primary-500/40"
    >
      <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${tone}`}>
        <Icon size={20} />
      </div>
      <div className="min-w-0">
        <p className="truncate text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
        <p className="truncate text-xl font-bold">{value}</p>
        {sub && <p className="truncate text-xs text-slate-400">{sub}</p>}
      </div>
    </button>
  );
}

function ChartCard({
  title, icon: Icon, onViewData, children,
}: {
  title: string;
  icon?: any;
  onViewData: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-semibold">
          {Icon && <Icon size={16} className="text-primary-600" />}
          {title}
        </h2>
        <button
          className="btn-ghost !px-2 !py-1 text-xs text-slate-400 hover:text-primary-600"
          onClick={onViewData}
          title="View & export the underlying data"
        >
          <Table2 size={14} /> Data
        </button>
      </div>
      {children}
    </div>
  );
}

// --- page -----------------------------------------------------------------

export default function Dashboard() {
  const { user } = useAuth();
  const [preset, setPreset] = useState<PresetKey>("12m");
  const [range, setRange] = useState(() => presetRange("12m"));
  const [drilldown, setDrilldown] = useState<DrilldownTarget | null>(null);

  const { start, end } = range;

  const { data, isLoading } = useQuery({
    queryKey: ["dashboard", start, end],
    queryFn: async () => (await api.get("/reports/dashboard", { params: { start, end } })).data,
    enabled: !!start && !!end && start <= end,
  });

  const open = (metric: string, label: string) => setDrilldown({ metric, label });

  if (isLoading || !data) return <PageSpinner />;

  const { kpis, granularity } = data;
  const revenueSeries = data.revenue_series.map((r: any) => ({ ...r, label: periodLabel(r.period, granularity) }));
  const conversionSeries = data.lead_conversion.map((r: any) => ({ ...r, label: periodLabel(r.period, granularity) }));
  const tasksOverview = data.tasks_overview.map((r: any) => ({
    ...r,
    label: r.status.replace("_", " "),
  }));
  const winRateData = [
    { name: "Won", value: data.win_rate.won },
    { name: "Lost", value: data.win_rate.lost },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Good day, {user?.first_name}!</h1>
          <p className="text-sm text-slate-400">
            Showing {formatDate(start)} – {formatDate(end)} · click any KPI or chart to inspect and export its data.
          </p>
        </div>
        <DateRangePicker
          preset={preset}
          start={start}
          end={end}
          onChange={(nextPreset, nextStart, nextEnd) => {
            setPreset(nextPreset);
            setRange({ start: nextStart, end: nextEnd });
          }}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <KpiCard
          label="Revenue (won)"
          value={formatMoney(kpis.revenue)}
          sub={`${kpis.won_deals} deal${kpis.won_deals === 1 ? "" : "s"} won`}
          icon={IndianRupee}
          tone="bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300"
          onClick={() => open("revenue", "Revenue — won deals")}
        />
        <KpiCard
          label="Active Leads"
          value={kpis.active_leads}
          sub="new · contacted · qualified"
          icon={Target}
          tone="bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300"
          onClick={() => open("active_leads", "Active leads")}
        />
        <KpiCard
          label="Open Deals"
          value={kpis.open_deals}
          sub={formatMoney(kpis.open_deals_value)}
          icon={Briefcase}
          tone="bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300"
          onClick={() => open("open_deals", "Open deals")}
        />
        <KpiCard
          label="Won Deals"
          value={kpis.won_deals}
          sub={`${data.win_rate.win_rate}% win rate`}
          icon={Trophy}
          tone="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300"
          onClick={() => open("won_deals", "Won deals")}
        />
        <KpiCard
          label="Tasks Due"
          value={kpis.tasks_due}
          sub="open tasks due in period"
          icon={CheckSquare}
          tone="bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300"
          onClick={() => open("tasks_due", "Tasks due in period")}
        />
        <KpiCard
          label="Meetings"
          value={kpis.meetings}
          sub="scheduled in period"
          icon={CalendarDays}
          tone="bg-rose-100 text-rose-700 dark:bg-rose-900/50 dark:text-rose-300"
          onClick={() => open("meetings", "Meetings in period")}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartCard title="Revenue Over Time" onViewData={() => open("revenue_series", "Revenue — won deals")}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={revenueSeries}>
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
              <XAxis dataKey="label" fontSize={12} tickLine={false} interval="preserveStartEnd" />
              <YAxis fontSize={12} tickLine={false} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
              <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
              <Bar dataKey="revenue" fill="#4F46E5" radius={[4, 4, 0, 0]} name="Revenue" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Lead Conversion" onViewData={() => open("lead_conversion", "Leads created in period")}>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={conversionSeries}>
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
              <XAxis dataKey="label" fontSize={12} tickLine={false} interval="preserveStartEnd" />
              <YAxis fontSize={12} tickLine={false} allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="created" stroke="#64748B" strokeWidth={2} dot={false} name="New leads" />
              <Line type="monotone" dataKey="converted" stroke="#10B981" strokeWidth={2} dot={false} name="Converted" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Open Pipeline by Stage" onViewData={() => open("pipeline_by_stage", "Open deals by stage")}>
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
        </ChartCard>

        <ChartCard title="Lead Sources" onViewData={() => open("lead_sources", "Leads by source")}>
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
        </ChartCard>

        <ChartCard title={`Win Rate — ${data.win_rate.win_rate}%`} onViewData={() => open("win_rate", "Closed deals (won + lost)")}>
          {data.win_rate.won + data.win_rate.lost === 0 ? (
            <p className="py-16 text-center text-sm text-slate-400">No deals closed in this period.</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={winRateData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={2}>
                  <Cell fill="#10B981" />
                  <Cell fill="#EF4444" />
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Tasks Overview" onViewData={() => open("tasks_overview", "Tasks created in period")}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={tasksOverview}>
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
              <XAxis dataKey="label" fontSize={12} tickLine={false} className="capitalize" />
              <YAxis fontSize={12} tickLine={false} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#8B5CF6" radius={[4, 4, 0, 0]} name="Tasks" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Whose birthday is coming up — the daily prompt an agent actually acts on. */}
      <BirthdayPanel compact />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <ChartCard title="Upcoming Meetings" icon={CalendarClock} onViewData={() => open("upcoming_meetings", "Meetings in period")}>
          {data.upcoming_meetings.length === 0 && <p className="text-sm text-slate-400">No meetings in this period.</p>}
          <ul className="space-y-2.5">
            {data.upcoming_meetings.map((m: any) => (
              <li key={m.id} className="rounded-lg border border-slate-100 p-2.5 text-sm dark:border-slate-800">
                <p className="font-medium">{m.title}</p>
                <p className="text-xs text-slate-400">
                  {formatDateTime(m.starts_at)}
                  {m.location ? ` · ${m.location}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </ChartCard>

        <ChartCard title="Recent Activity" icon={CheckSquare} onViewData={() => open("recent_activities", "Activities in period")}>
          {data.recent_activities.length === 0 && <p className="text-sm text-slate-400">No activity in this period.</p>}
          <ul className="space-y-2.5">
            {data.recent_activities.map((a: any) => (
              <li key={a.id} className="flex items-start gap-2 text-sm">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary-500" />
                <div className="min-w-0">
                  <p className="truncate">{a.title}</p>
                  <p className="text-xs text-slate-400">
                    {a.user ? `${a.user} · ` : ""}
                    {timeAgo(a.created_at)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </ChartCard>

        <ChartCard title="Top Performers" icon={Trophy} onViewData={() => open("team_performance", "Deals by owner")}>
          {data.team_performance.length === 0 && <p className="text-sm text-slate-400">No owned deals in this period.</p>}
          <ul className="space-y-2.5">
            {data.team_performance.map((p: any) => {
              const [first, ...rest] = String(p.name).split(" ");
              return (
                <li key={p.user_id} className="flex items-center gap-3 text-sm">
                  <Avatar first={first} last={rest.join(" ")} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{p.name}</p>
                    <p className="text-xs text-slate-400">
                      {p.won_count} won · {p.open_count} open
                    </p>
                  </div>
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">{formatMoney(p.won_value)}</span>
                </li>
              );
            })}
          </ul>
        </ChartCard>
      </div>

      <DrilldownModal target={drilldown} start={start} end={end} onClose={() => setDrilldown(null)} />
    </div>
  );
}
