import { useQuery } from "@tanstack/react-query";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { PageSpinner } from "@/components/ui";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";

const COLORS = ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#64748B", "#8B5CF6", "#0EA5E9", "#EC4899"];

export default function Reports() {
  const funnel = useQuery({ queryKey: ["r-funnel"], queryFn: async () => (await api.get("/reports/funnel")).data });
  const sources = useQuery({ queryKey: ["r-sources"], queryFn: async () => (await api.get("/reports/lead-sources")).data });
  const winRate = useQuery({ queryKey: ["r-win"], queryFn: async () => (await api.get("/reports/win-rate")).data });
  const growth = useQuery({ queryKey: ["r-growth"], queryFn: async () => (await api.get("/reports/customer-growth")).data });
  const activity = useQuery({ queryKey: ["r-activity"], queryFn: async () => (await api.get("/reports/activity")).data });

  if (funnel.isLoading || sources.isLoading || winRate.isLoading) return <PageSpinner />;

  const monthLabel = (m: string) => new Date(`${m}-01`).toLocaleDateString(undefined, { month: "short" });
  const growthData = (growth.data ?? []).map((r: any) => ({ ...r, label: monthLabel(r.month) }));
  const wr = winRate.data ?? { won: 0, lost: 0, open: 0, win_rate: 0 };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Reports</h1>
        <p className="text-sm text-slate-400">Sales performance across the organisation.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card p-4">
          <h2 className="mb-3 font-semibold">Sales Funnel</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={funnel.data ?? []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
              <XAxis type="number" fontSize={12} allowDecimals={false} />
              <YAxis type="category" dataKey="stage" fontSize={12} width={90} />
              <Tooltip formatter={(v: any, name: any) => (name === "value" ? formatMoney(Number(v)) : v)} />
              <Bar dataKey="count" fill="#4F46E5" radius={[0, 4, 4, 0]} name="Deals" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-4">
          <h2 className="mb-3 font-semibold">Lead Sources</h2>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={sources.data ?? []}
                dataKey="count"
                nameKey="source"
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={90}
                paddingAngle={2}
              >
                {(sources.data ?? []).map((_: any, i: number) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-4">
          <h2 className="mb-3 font-semibold">Win Rate</h2>
          <div className="mb-3 flex items-center gap-6">
            <p className="text-4xl font-bold text-primary-600 dark:text-primary-400">{wr.win_rate}%</p>
            <div className="text-sm text-slate-500">
              <p>
                <span className="font-semibold text-emerald-600">{wr.won}</span> won ·{" "}
                <span className="font-semibold text-red-500">{wr.lost}</span> lost ·{" "}
                <span className="font-semibold">{wr.open}</span> open
              </p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie
                data={[
                  { name: "Won", value: wr.won },
                  { name: "Lost", value: wr.lost },
                  { name: "Open", value: wr.open },
                ]}
                dataKey="value"
                cx="50%"
                cy="50%"
                outerRadius={70}
              >
                <Cell fill="#10B981" />
                <Cell fill="#EF4444" />
                <Cell fill="#64748B" />
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-4">
          <h2 className="mb-3 font-semibold">Customer Growth</h2>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={growthData}>
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
              <XAxis dataKey="label" fontSize={12} tickLine={false} />
              <YAxis fontSize={12} allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="count" stroke="#4F46E5" strokeWidth={2} name="New companies" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-4 xl:col-span-2">
          <h2 className="mb-3 font-semibold">Activity (last 30 days)</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={activity.data ?? []}>
              <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
              <XAxis dataKey="type" fontSize={12} />
              <YAxis fontSize={12} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#10B981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
