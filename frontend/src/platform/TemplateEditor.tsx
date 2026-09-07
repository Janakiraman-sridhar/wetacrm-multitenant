import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDown, ArrowUp, GripVertical, Lock, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { moduleIcon } from "@/lib/modules";
import type { CrmTemplateDetail } from "@/types";

interface CatalogModule {
  key: string;
  label: string;
  order: number;
  icon: string;
  locked: boolean;
  permission: string | null;
}

interface TemplateModule {
  key: string;
  enabled: boolean;
  label?: string;
  order?: number;
}

interface Stage {
  name: string;
  order?: number;
  probability?: number;
  is_won?: boolean;
  is_lost?: boolean;
}

/**
 * Customise a template — which modules a new client gets, what they are called, and
 * the pipeline they start with.
 *
 * Only custom templates are editable. A system template is refreshed from the
 * product whenever its version increases, so an edit to one would be silently
 * overwritten; the backend refuses, and this offers Clone instead.
 *
 * Editing a template changes nothing for tenants already created from it — they own
 * their configuration outright. It shapes the *next* workspace made from it.
 */
export function TemplateEditor({
  templateKey,
  onClone,
}: {
  templateKey: string;
  onClone: () => void;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [modules, setModules] = useState<TemplateModule[]>([]);
  const [stages, setStages] = useState<Stage[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [newStage, setNewStage] = useState("");
  const [newSource, setNewSource] = useState("");

  const { data: template } = useQuery({
    queryKey: ["platform", "template", templateKey],
    queryFn: async () =>
      (await api.get<CrmTemplateDetail>(`/platform/templates/${templateKey}`)).data,
  });
  const { data: catalog } = useQuery({
    queryKey: ["platform", "module-catalog"],
    queryFn: async () => (await api.get<CatalogModule[]>("/platform/module-catalog")).data,
    staleTime: 10 * 60_000,
  });

  useEffect(() => {
    if (!template || !catalog) return;
    const configured = new Map<string, TemplateModule>(
      (template.config.modules ?? []).map((m: TemplateModule) => [m.key, m])
    );
    // Every catalog module appears, so an admin can switch on one the template
    // never mentioned without knowing it exists.
    setModules(
      catalog
        .map((entry) => {
          const found = configured.get(entry.key);
          return {
            key: entry.key,
            enabled: found ? found.enabled : true,
            label: found?.label ?? entry.label,
            order: found?.order ?? entry.order,
          };
        })
        .sort((a, b) => (a.order ?? 99) - (b.order ?? 99))
    );
    setStages(template.config.stages ?? []);
    setSources(template.config.lead_sources ?? []);
  }, [template, catalog]);

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.patch(`/platform/templates/${templateKey}`, {
          modules: modules.map((m, index) => ({ ...m, order: index + 1 })),
          stages: stages.map((s, index) => ({ ...s, order: index + 1 })),
          lead_sources: sources,
        })
      ).data,
    onSuccess: () => {
      toast("Template updated");
      queryClient.invalidateQueries({ queryKey: ["platform", "template", templateKey] });
      queryClient.invalidateQueries({ queryKey: ["platform", "templates"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  if (!template || !catalog) return <p className="text-slate-400">Loading…</p>;

  const locked = new Map(catalog.map((m) => [m.key, m.locked]));

  if (template.is_system) {
    return (
      <div className="space-y-3">
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          <p className="font-medium">{template.name} is a system template.</p>
          <p className="mt-1">
            It is refreshed from the product whenever it changes, so any edit here would be
            overwritten. Clone it to get a copy that is yours to customise — existing tenants
            are unaffected either way.
          </p>
        </div>
        <button className="btn-primary" onClick={onClone}>
          Clone {template.name} to customise
        </button>
      </div>
    );
  }

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= modules.length) return;
    const next = [...modules];
    [next[index], next[target]] = [next[target], next[index]];
    setModules(next);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Shapes the <strong>next</strong> workspace created from this template. Tenants that
          already exist keep the configuration they were given.
        </p>
        <button className="btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
          <Save size={15} /> {save.isPending ? "Saving…" : "Save template"}
        </button>
      </div>

      <section>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
          Modules · order and labels
        </h3>
        <div className="card divide-y divide-slate-100 px-3 dark:divide-slate-800">
          {modules.map((m, index) => {
            const Icon = moduleIcon(catalog.find((c) => c.key === m.key)?.icon ?? "Circle");
            const isLocked = locked.get(m.key);
            return (
              <div key={m.key} className="flex items-center gap-2 py-2">
                <GripVertical size={14} className="shrink-0 text-slate-300" />
                <Icon size={15} className="shrink-0 text-primary-600 dark:text-primary-400" />
                <code className="w-28 shrink-0 truncate text-xs text-slate-400">{m.key}</code>
                <input
                  className="input !py-1.5 flex-1"
                  value={m.label ?? ""}
                  onChange={(e) =>
                    setModules(modules.map((x, i) => (i === index ? { ...x, label: e.target.value } : x)))
                  }
                  aria-label={`Label for ${m.key}`}
                />
                <button className="btn-ghost !p-1" onClick={() => move(index, -1)} title="Move up">
                  <ArrowUp size={12} />
                </button>
                <button className="btn-ghost !p-1" onClick={() => move(index, 1)} title="Move down">
                  <ArrowDown size={12} />
                </button>
                <label
                  className={clsx(
                    "flex w-16 shrink-0 items-center gap-1.5 text-xs",
                    isLocked ? "cursor-not-allowed text-slate-400" : "cursor-pointer"
                  )}
                  title={isLocked ? "This module cannot be switched off" : undefined}
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-primary-600"
                    checked={isLocked ? true : m.enabled}
                    disabled={isLocked}
                    onChange={(e) =>
                      setModules(
                        modules.map((x, i) => (i === index ? { ...x, enabled: e.target.checked } : x))
                      )
                    }
                  />
                  {isLocked ? <Lock size={12} /> : "On"}
                </label>
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
          Pipeline stages
        </h3>
        <div className="card p-3">
          <ul className="space-y-1">
            {stages.map((stage, index) => (
              <li key={`${stage.name}-${index}`} className="flex items-center gap-2">
                <span className="w-6 text-center text-xs text-slate-400">{index + 1}</span>
                <input
                  className="input !py-1.5 flex-1"
                  value={stage.name}
                  onChange={(e) =>
                    setStages(stages.map((s, i) => (i === index ? { ...s, name: e.target.value } : s)))
                  }
                />
                <label className="flex shrink-0 cursor-pointer items-center gap-1 text-xs text-emerald-600">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-emerald-600"
                    checked={!!stage.is_won}
                    onChange={(e) =>
                      setStages(
                        stages.map((s, i) =>
                          i === index ? { ...s, is_won: e.target.checked, is_lost: false } : s
                        )
                      )
                    }
                  />
                  Won
                </label>
                <label className="flex shrink-0 cursor-pointer items-center gap-1 text-xs text-red-500">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-red-500"
                    checked={!!stage.is_lost}
                    onChange={(e) =>
                      setStages(
                        stages.map((s, i) =>
                          i === index ? { ...s, is_lost: e.target.checked, is_won: false } : s
                        )
                      )
                    }
                  />
                  Lost
                </label>
                <button
                  className="btn-ghost !p-1 text-red-500"
                  onClick={() => setStages(stages.filter((_, i) => i !== index))}
                >
                  <Trash2 size={12} />
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex gap-2">
            <input
              className="input !py-1.5"
              placeholder="Add a stage…"
              value={newStage}
              onChange={(e) => setNewStage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newStage.trim()) {
                  setStages([...stages, { name: newStage.trim(), probability: 50 }]);
                  setNewStage("");
                }
              }}
            />
            <button
              className="btn-secondary shrink-0"
              disabled={!newStage.trim()}
              onClick={() => {
                setStages([...stages, { name: newStage.trim(), probability: 50 }]);
                setNewStage("");
              }}
            >
              <Plus size={14} /> Add
            </button>
          </div>
        </div>
      </section>

      <section>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
          Lead sources
        </h3>
        <div className="card p-3">
          <div className="flex flex-wrap gap-1.5">
            {sources.map((source, index) => (
              <span key={`${source}-${index}`} className="badge bg-slate-100 dark:bg-slate-800">
                {source}
                <button
                  className="ml-1.5 text-slate-400 hover:text-red-500"
                  onClick={() => setSources(sources.filter((_, i) => i !== index))}
                >
                  ×
                </button>
              </span>
            ))}
            {sources.length === 0 && <span className="text-sm text-slate-400">None yet.</span>}
          </div>
          <div className="mt-2 flex gap-2">
            <input
              className="input !py-1.5"
              placeholder="Add a source…"
              value={newSource}
              onChange={(e) => setNewSource(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newSource.trim()) {
                  setSources([...sources, newSource.trim()]);
                  setNewSource("");
                }
              }}
            />
            <button
              className="btn-secondary shrink-0"
              disabled={!newSource.trim()}
              onClick={() => {
                setSources([...sources, newSource.trim()]);
                setNewSource("");
              }}
            >
              <Plus size={14} /> Add
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
