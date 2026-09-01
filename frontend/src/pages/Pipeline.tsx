import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";

import { Avatar, PageSpinner } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { Deal, PipelineColumn } from "@/types";

export default function Pipeline() {
  const { hasPerm } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [dragId, setDragId] = useState<string | null>(null);
  const [overStage, setOverStage] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["pipeline"],
    queryFn: async () => (await api.get<PipelineColumn[]>("/deals/pipeline")).data,
  });

  const moveMutation = useMutation({
    mutationFn: async ({ dealId, stageId }: { dealId: string; stageId: string }) =>
      (await api.post(`/deals/${dealId}/move`, { stage_id: stageId })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pipeline"] });
      queryClient.invalidateQueries({ queryKey: ["/deals"] });
    },
    onError: (err) => {
      toast(errorMessage(err), "error");
      queryClient.invalidateQueries({ queryKey: ["pipeline"] });
    },
  });

  if (isLoading || !data) return <PageSpinner />;

  const canWrite = hasPerm("deals:write");

  const onDrop = (stageId: string) => {
    setOverStage(null);
    if (!dragId || !canWrite) return;
    // Optimistic update
    queryClient.setQueryData<PipelineColumn[]>(["pipeline"], (cols) => {
      if (!cols) return cols;
      let moved: Deal | undefined;
      const stripped = cols.map((c) => {
        const found = c.deals.find((d) => d.id === dragId);
        if (found) moved = found;
        return { ...c, deals: c.deals.filter((d) => d.id !== dragId) };
      });
      if (!moved) return cols;
      return stripped.map((c) =>
        c.stage.id === stageId
          ? { ...c, deals: [moved!, ...c.deals], total_value: c.total_value + Number(moved!.value || 0) }
          : c
      );
    });
    moveMutation.mutate({ dealId: dragId, stageId });
    setDragId(null);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Sales Pipeline</h1>
        <p className="text-sm text-slate-400">Drag deals between stages to update them.</p>
      </div>

      <div className="flex gap-3 overflow-x-auto pb-4">
        {data.map((col) => (
          <div
            key={col.stage.id}
            className={clsx(
              "flex w-72 shrink-0 flex-col rounded-xl border bg-slate-100/60 dark:bg-slate-900/60",
              overStage === col.stage.id
                ? "border-primary-400 ring-2 ring-primary-400/30"
                : "border-slate-200 dark:border-slate-800"
            )}
            onDragOver={(e) => {
              e.preventDefault();
              setOverStage(col.stage.id);
            }}
            onDragLeave={() => setOverStage((s) => (s === col.stage.id ? null : s))}
            onDrop={() => onDrop(col.stage.id)}
          >
            <div className="flex items-center justify-between px-3 py-2.5">
              <div className="flex items-center gap-2">
                <span
                  className={clsx(
                    "h-2 w-2 rounded-full",
                    col.stage.is_won ? "bg-emerald-500" : col.stage.is_lost ? "bg-red-500" : "bg-primary-500"
                  )}
                />
                <span className="text-sm font-semibold">{col.stage.name}</span>
                <span className="rounded-full bg-slate-200 px-1.5 text-xs text-slate-500 dark:bg-slate-800">
                  {col.deals.length}
                </span>
              </div>
              <span className="text-xs font-medium text-slate-400">{formatMoney(col.total_value)}</span>
            </div>

            <div className="flex min-h-24 flex-1 flex-col gap-2 px-2 pb-2">
              {col.deals.map((deal) => (
                <div
                  key={deal.id}
                  draggable={canWrite}
                  onDragStart={() => setDragId(deal.id)}
                  onDragEnd={() => setDragId(null)}
                  className={clsx(
                    "card cursor-grab p-3 text-sm transition-shadow hover:shadow-md active:cursor-grabbing",
                    dragId === deal.id && "opacity-50"
                  )}
                >
                  <p className="font-medium leading-snug">{deal.title}</p>
                  <p className="mt-0.5 text-xs text-slate-400">{deal.company?.name ?? "No company"}</p>
                  <div className="mt-2 flex items-center justify-between">
                    <span className="badge bg-primary-50 font-semibold text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">
                      {formatMoney(deal.value, deal.currency)}
                    </span>
                    {deal.owner && <Avatar first={deal.owner.first_name} last={deal.owner.last_name} size={22} />}
                  </div>
                </div>
              ))}
              {col.deals.length === 0 && (
                <p className="py-6 text-center text-xs text-slate-400">Drop deals here</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
