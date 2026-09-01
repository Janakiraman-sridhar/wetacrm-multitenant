import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useToast } from "@/context/ToastContext";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { connectSocket } from "@/lib/socket";
import type { Notification, Page } from "@/types";

export function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const navigate = useNavigate();

  const { data: countData } = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: async () => (await api.get<{ count: number }>("/notifications/unread-count")).data,
    refetchInterval: 60_000,
  });

  const { data: list } = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: async () => (await api.get<Page<Notification>>("/notifications", { params: { page_size: 15 } })).data,
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

  const unread = countData?.count ?? 0;

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
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="fixed inset-0 z-50" onClick={() => setOpen(false)}>
          <div
            className="absolute right-0 top-0 flex h-full w-full max-w-sm flex-col border-l border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
              <h2 className="font-semibold">Notifications</h2>
              <div className="flex gap-1">
                <button className="btn-ghost !p-1.5" title="Mark all read" onClick={markAllRead}>
                  <CheckCheck size={16} />
                </button>
                <button className="btn-ghost !p-1.5" onClick={() => setOpen(false)}>
                  <X size={16} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              {(list?.items ?? []).length === 0 && (
                <p className="py-16 text-center text-sm text-slate-400">You're all caught up 🎉</p>
              )}
              {(list?.items ?? []).map((n) => (
                <button
                  key={n.id}
                  onClick={() => openNotification(n)}
                  className={`block w-full border-b border-slate-100 px-4 py-3 text-left transition-colors hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50 ${
                    n.is_read ? "opacity-60" : ""
                  }`}
                >
                  <p className="text-sm font-medium">{n.title}</p>
                  {n.body && <p className="mt-0.5 text-xs text-slate-500">{n.body}</p>}
                  <p className="mt-1 text-[11px] text-slate-400">{timeAgo(n.created_at)}</p>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
