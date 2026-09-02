import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Bell, BellOff, CalendarClock, CheckCheck, FolderKanban, LifeBuoy, ListTodo,
  Target, TrendingUp, X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useToast } from "@/context/ToastContext";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { connectSocket } from "@/lib/socket";
import type { Notification, Page } from "@/types";

const TYPE_STYLES: Record<string, { icon: any; tone: string }> = {
  lead_assigned: { icon: Target, tone: "bg-sky-100 text-sky-600 dark:bg-sky-900/50 dark:text-sky-300" },
  deal_updated: { icon: TrendingUp, tone: "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-300" },
  task_assigned: { icon: ListTodo, tone: "bg-violet-100 text-violet-600 dark:bg-violet-900/50 dark:text-violet-300" },
  meeting_reminder: { icon: CalendarClock, tone: "bg-rose-100 text-rose-600 dark:bg-rose-900/50 dark:text-rose-300" },
  meeting_invite: { icon: CalendarClock, tone: "bg-rose-100 text-rose-600 dark:bg-rose-900/50 dark:text-rose-300" },
  ticket_assigned: { icon: LifeBuoy, tone: "bg-amber-100 text-amber-600 dark:bg-amber-900/50 dark:text-amber-300" },
  project_assigned: { icon: FolderKanban, tone: "bg-indigo-100 text-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-300" },
};

const DEFAULT_STYLE = { icon: Bell, tone: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300" };

export function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const navigate = useNavigate();

  const { data: countData } = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: async () => (await api.get<{ count: number }>("/notifications/unread-count")).data,
    refetchInterval: 60_000,
  });

  const { data: list } = useQuery({
    queryKey: ["notifications", "list", filter],
    queryFn: async () =>
      (
        await api.get<Page<Notification>>("/notifications", {
          params: { page_size: 30, unread_only: filter === "unread" || undefined },
        })
      ).data,
    enabled: open,
  });

  useEffect(() => {
    const socket = connectSocket();
    if (!socket) return;
    const handler = (n: any) => {
      toast(n.title, "info");
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    };
    socket.on("notification", handler);
    return () => {
      socket.off("notification", handler);
    };
  }, [queryClient, toast]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const unread = countData?.count ?? 0;
  const items = list?.items ?? [];

  const markAllRead = async () => {
    await api.post("/notifications/read-all");
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };

  const openNotification = async (n: Notification) => {
    if (!n.is_read) {
      await api.post(`/notifications/${n.id}/read`);
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }
    if (n.link) {
      setOpen(false);
      navigate(n.link);
    }
  };

  return (
    <>
      <button className="btn-ghost relative !p-2" onClick={() => setOpen(true)} title="Notifications">
        <Bell size={18} strokeWidth={1.8} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white ring-2 ring-white dark:ring-slate-900">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 bg-slate-900/30 backdrop-blur-[2px]" onClick={() => setOpen(false)}>
          <div
            className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-100 text-primary-600 dark:bg-primary-900/50 dark:text-primary-300">
                  <Bell size={17} />
                </span>
                <div>
                  <h2 className="font-semibold leading-tight">Notifications</h2>
                  <p className="text-xs text-slate-400">
                    {unread > 0 ? `${unread} unread` : "All caught up"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                {unread > 0 && (
                  <button
                    className="btn-ghost !px-2 !py-1.5 text-xs text-primary-600 dark:text-primary-400"
                    onClick={markAllRead}
                  >
                    <CheckCheck size={14} /> Mark all read
                  </button>
                )}
                <button className="btn-ghost !p-1.5" onClick={() => setOpen(false)} title="Close (Esc)">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Filter */}
            <div className="border-b border-slate-200 px-5 py-2.5 dark:border-slate-800">
              <div className="flex w-fit rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-slate-700 dark:bg-slate-800">
                {(["all", "unread"] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={clsx(
                      "rounded-md px-3.5 py-1 text-xs font-medium capitalize transition-colors",
                      filter === f
                        ? "bg-white text-primary-700 shadow-sm dark:bg-slate-900 dark:text-primary-300"
                        : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                    )}
                  >
                    {f}
                    {f === "unread" && unread > 0 && (
                      <span className="ml-1.5 rounded-full bg-red-100 px-1.5 text-[10px] font-bold text-red-600 dark:bg-red-900/50 dark:text-red-300">
                        {unread}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto">
              {items.length === 0 && (
                <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
                  <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-300 dark:bg-slate-800 dark:text-slate-600">
                    <BellOff size={24} />
                  </span>
                  <p className="font-medium text-slate-500 dark:text-slate-300">
                    {filter === "unread" ? "No unread notifications" : "No notifications yet"}
                  </p>
                  <p className="text-xs text-slate-400">
                    Assignments, deal updates and meeting reminders will land here.
                  </p>
                </div>
              )}
              {items.map((n) => {
                const style = TYPE_STYLES[n.type] ?? DEFAULT_STYLE;
                const Icon = style.icon;
                return (
                  <button
                    key={n.id}
                    onClick={() => openNotification(n)}
                    className={clsx(
                      "flex w-full items-start gap-3 border-b border-slate-100 px-5 py-3.5 text-left transition-colors hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50",
                      !n.is_read && "bg-primary-50/40 dark:bg-primary-900/10"
                    )}
                  >
                    <span className={clsx("mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl", style.tone)}>
                      <Icon size={16} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className={clsx("block text-sm leading-snug", n.is_read ? "text-slate-500 dark:text-slate-400" : "font-medium")}>
                        {n.title}
                      </span>
                      {n.body && <span className="mt-0.5 block truncate text-xs text-slate-400">{n.body}</span>}
                      <span className="mt-1 block text-[11px] text-slate-400">{timeAgo(n.created_at)}</span>
                    </span>
                    {!n.is_read && <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-primary-500" />}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
