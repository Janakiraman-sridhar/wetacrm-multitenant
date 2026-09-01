import { useQuery } from "@tanstack/react-query";
import { Briefcase, CalendarClock, CheckSquare, IndianRupee, Target, Trophy } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { Avatar, PageSpinner } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { formatDateTime, formatMoney, timeAgo } from "@/lib/format";

function KpiCard({
  label,
  value,
  sub,
  icon: Icon,
  tone,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: any;
  tone: string;
}) {
  return (
    <div className="card flex items-center gap-4 p-4">
      <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${tone}`}>
        <Icon size={20} />
      </div>
      <div className="min-w-0">
        <p className="truncate text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
        <p className="truncate text-xl font-bold">{value}</p>
        {sub && <p className="truncate text-xs text-slate-400">{sub}</p>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => (await api.get("/reports/dashboard")).data,
  });

  if (isLoading || !data) return <PageSpinner />;

  const { kpis } = data;
  const monthLabel = (m: string) => new Date(`${m}-01`).toLocaleDateString(undefined, { month: "short" });
  const sales = data.monthly_sales.map((r: any) => ({ ...r, label: monthLabel(r.month) }));
  const conversion = data.lead_conversion.map((r: any) => ({ ...r, label: monthLabel(r.month) }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Good day, {user?.first_name} 👋</h1>
        <p className="text-sm text-slate-400">Here's what's happening across your sales organisation.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Total Revenue"
          value={formatMoney(kpis.revenue)}
          sub={`${formatMoney(kpis.revenue_this_month)} this month`}
          icon={IndianRupee}
          tone="bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300"
        />
        <KpiCard
          label="Active Leads"
          value={kpis.active_leads}
          icon={Target}
          tone="bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300"
        />
        <KpiCard
          label="Open Deals"
          value={kpis.open_deals}
          sub={formatMoney(kpis.open_deals_value)}
          icon={Briefcase}
          tone="bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300"
        />
        <KpiCard
          label="Won Deals"
          value={kpis.won_deals}
          sub={`${kpis.tasks_due_today} tasks due today`}
          icon={Trophy}
          tone="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">Monthly Revenue</h2>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={sales}>
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
              <XAxis dataKey="label" fontSize={12} tickLine={false} />
              <YAxis fontSize={12} tickLine={false} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
              <Tooltip formatter={(v: any) => formatMoney(Number(v))} />
              <Bar dataKey="revenue" fill="#4F46E5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">Lead Conversion</h2>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={conversion}>
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
              <XAxis dataKey="label" fontSize={12} tickLine={false} />
              <YAxis fontSize={12} tickLine={false} allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="created" stroke="#64748B" strokeWidth={2} dot={false} name="New leads" />
              <Line type="monotone" dataKey="converted" stroke="#10B981" strokeWidth={2} dot={false} name="Converted" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="card p-4">
          <h2 className="mb-3 flex items-center gap-2 font-semibold">
            <CalendarClock size={16} className="text-primary-600" /> Upcoming Meetings
          </h2>
          {data.upcoming_meetings.length === 0 && <p className="text-sm text-slate-400">No upcoming meetings.</p>}
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
        </div>

        <div className="card p-4">
          <h2 className="mb-3 flex items-center gap-2 font-semibold">
            <CheckSquare size={16} className="text-primary-600" /> Recent Activity
          </h2>
          {data.recent_activities.length === 0 && <p className="text-sm text-slate-400">No activity yet.</p>}
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
        </div>

        <div className="card p-4">
          <h2 className="mb-3 flex items-center gap-2 font-semibold">
            <Trophy size={16} className="text-primary-600" /> Top Performers
          </h2>
          {data.team_performance.length === 0 && <p className="text-sm text-slate-400">No closed deals yet.</p>}
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
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                    {formatMoney(p.won_value)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
