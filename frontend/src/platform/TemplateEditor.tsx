import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowLeft, Check, ChevronRight, Flag, Lock, Plus, Save, Shield, Table2, Trash2, Trophy, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/Modal";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { CatalogModule, ModuleBoard, ModuleSetting, mergeWithCatalog } from "@/platform/ModuleBoard";
import type { CrmTemplateDetail } from "@/types";

interface Stage {
  name: string;
  order?: number;
  probability?: number;
  is_won?: boolean;
  is_lost?: boolean;
}

/** A stage is one of these three, never two — the old pair of checkboxes could be neither. */
type Outcome = "open" | "won" | "lost";

const outcomeOf = (s: Stage): Outcome => (s.is_won ? "won" : s.is_lost ? "lost" : "open");

const SECTIONS = [
  { id: "modules", label: "Modules" },
  { id: "pipeline", label: "Pipeline" },
  { id: "sources", label: "Lead sources" },
  { id: "roles", label: "Roles" },
] as const;

/**
 * Customise a template — what a workspace built from it gets on day one.
 *
 * This is a page rather than a dialog. It configures eighteen modules, a pipeline
 * and a source list; a scrolling modal gave no sense of how much there was, could
 * not be linked to or reloaded, and put the save button somewhere you lost as soon
 * as you scrolled.
 *
 * Editing a template changes nothing for tenants already built from it — they own
 * their configuration outright. It shapes the *next* workspace made from it, which
 * the page says once, plainly, rather than leaving it to be discovered.
 */
export default function TemplateEditor() {
  const { templateKey = "" } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [modules, setModules] = useState<ModuleSetting[]>([]);
  const [stages, setStages] = useState<Stage[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [newStage, setNewStage] = useState("");
  const [newSource, setNewSource] = useState("");
  const [section, setSection] = useState<string>("modules");
  const [leaving, setLeaving] = useState<null | (() => void)>(null);
  const saved = useRef("");

  const { data: template, isLoading } = useQuery({
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
    const merged = mergeWithCatalog(catalog, template.config.modules);
    const nextStages = template.config.stages ?? [];
    const nextSources = template.config.lead_sources ?? [];
    setModules(merged);
    setStages(nextStages);
    setSources(nextSources);
    saved.current = JSON.stringify([merged, nextStages, nextSources]);
  }, [template, catalog]);

  const dirty = useMemo(
    () => saved.current !== "" && JSON.stringify([modules, stages, sources]) !== saved.current,
    [modules, stages, sources]
  );

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
      toast("Template saved");
      saved.current = JSON.stringify([modules, stages, sources]);
      queryClient.invalidateQueries({ queryKey: ["platform", "template", templateKey] });
      queryClient.invalidateQueries({ queryKey: ["platform", "templates"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const leave = (then: () => void) => (dirty ? setLeaving(() => then) : then());
  const goBack = () => leave(() => navigate("/platform/templates"));

  if (isLoading || !template || !catalog) {
    return <p className="mx-auto max-w-6xl text-slate-400">Loading the template…</p>;
  }

  const readOnly = template.is_system;
  const setStage = (index: number, changes: Partial<Stage>) =>
    setStages(stages.map((s, i) => (i === index ? { ...s, ...changes } : s)));

  const addStage = () => {
    if (!newStage.trim()) return;
    setStages([...stages, { name: newStage.trim(), probability: 50 }]);
    setNewStage("");
  };

  const addSource = () => {
    const value = newSource.trim();
    if (!value || sources.includes(value)) return;
    setSources([...sources, value]);
    setNewSource("");
  };

  return (
    <div className="mx-auto max-w-6xl pb-10">
      {/* Sticky, because saving should never be somewhere you have to scroll to find. */}
      <div className="sticky top-0 z-20 -mx-3 mb-5 border-b border-slate-200 bg-slate-100/95 px-3 py-3 backdrop-blur sm:-mx-5 sm:px-5 dark:border-slate-800 dark:bg-slate-950/95">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
          <button className="btn-ghost !px-2" onClick={goBack} title="Back to templates">
            <ArrowLeft size={16} />
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="flex flex-wrap items-center gap-2 text-lg font-semibold">
              <span className="truncate">{template.name}</span>
              {readOnly && (
                <span className="badge bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  <Lock size={10} className="mr-1" /> system
                </span>
              )}
              {dirty && (
                <span className="badge bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                  unsaved
                </span>
              )}
            </h1>
            <p className="truncate text-xs text-slate-500 dark:text-slate-400">
              {template.key} · v{template.version} · shapes the <strong>next</strong> workspace made
              from it; existing ones keep what they were given
            </p>
          </div>
          {!readOnly && (
            <div className="flex shrink-0 items-center gap-2">
              {dirty && (
                <button
                  className="btn-secondary"
                  onClick={() => {
                    const [m, s, l] = JSON.parse(saved.current);
                    setModules(m);
                    setStages(s);
                    setSources(l);
                  }}
                >
                  Discard
                </button>
              )}
              <button className="btn-primary" disabled={save.isPending || !dirty} onClick={() => save.mutate()}>
                <Save size={15} />
                {save.isPending ? "Saving…" : dirty ? "Save changes" : "Saved"}
              </button>
            </div>
          )}
        </div>
      </div>

      {readOnly && (
        <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          <span className="flex-1">
            <strong>{template.name}</strong> ships with the product and is refreshed whenever it
            changes, so an edit here would be overwritten. Everything below is read-only — clone it
            for a copy that is yours.
          </span>
          <button
            className="btn-primary shrink-0"
            onClick={() => navigate(`/platform/templates?clone=${template.key}`)}
          >
            Clone to customise
          </button>
        </div>
      )}

      <nav className="mb-4 flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-800">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => setSection(s.id)}
            className={clsx(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              section === s.id
                ? "border-primary-600 text-primary-700 dark:border-primary-400 dark:text-primary-300"
                : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            )}
          >
            {s.label}
          </button>
        ))}
      </nav>

      {section === "modules" && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            What a new workspace can open, in the order they will see it, under the names they
            will read. Anything on the right is switched off for them — not hidden, but refused
            at the API too.
          </p>
          <ModuleBoard
            catalog={catalog}
            value={modules}
            onChange={setModules}
            disabled={readOnly}
          />
        </div>
      )}

      {section === "pipeline" && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            The stages a deal moves through. Mark the one that means the deal is won and the one
            that means it is lost — reporting counts them, so a pipeline with neither reports a
            0% win rate for ever.
          </p>
          <div className="card divide-y divide-slate-100 dark:divide-slate-800">
            {stages.map((stage, index) => (
              <div key={index} className="flex flex-wrap items-center gap-2 p-2.5">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-slate-100 text-xs font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                  {index + 1}
                </span>
                <input
                  className="input !py-1.5 min-w-0 flex-1"
                  value={stage.name}
                  disabled={readOnly}
                  onChange={(e) => setStage(index, { name: e.target.value })}
                />
                {/* One choice, not two checkboxes that quietly clear each other. */}
                <div className="flex shrink-0 overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
                  {([
                    ["open", "Open", ChevronRight],
                    ["won", "Won", Trophy],
                    ["lost", "Lost", Flag],
                  ] as const).map(([id, label, Icon]) => {
                    const active = outcomeOf(stage) === id;
                    return (
                      <button
                        key={id}
                        disabled={readOnly}
                        title={
                          id === "open" ? "Still in play"
                            : id === "won" ? "Reaching here counts as a win"
                              : "Reaching here counts as a loss"
                        }
                        onClick={() =>
                          setStage(index, { is_won: id === "won", is_lost: id === "lost" })
                        }
                        className={clsx(
                          "flex items-center gap-1 px-2 py-1.5 text-xs font-medium transition-colors",
                          active && id === "won" && "bg-emerald-500 text-white",
                          active && id === "lost" && "bg-red-500 text-white",
                          active && id === "open" && "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-100",
                          !active && "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                        )}
                      >
                        <Icon size={12} /> {label}
                      </button>
                    );
                  })}
                </div>
                <button
                  className="btn-ghost !p-1.5 shrink-0 text-slate-400 hover:text-red-500"
                  title="Remove this stage"
                  disabled={readOnly}
                  onClick={() => setStages(stages.filter((_, i) => i !== index))}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {stages.length === 0 && (
              <p className="px-3 py-6 text-center text-sm text-slate-400">
                No stages — a workspace made from this would have an empty pipeline.
              </p>
            )}
          </div>
          {!readOnly && (
            <div className="flex gap-2">
              <input
                className="input"
                placeholder="Add a stage…"
                value={newStage}
                onChange={(e) => setNewStage(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addStage()}
              />
              <button className="btn-secondary shrink-0" disabled={!newStage.trim()} onClick={addStage}>
                <Plus size={14} /> Add stage
              </button>
            </div>
          )}
        </div>
      )}

      {section === "sources" && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Where this client&rsquo;s leads come from. These fill the &ldquo;Source&rdquo; dropdown
            on day one; the workspace can add its own later.
          </p>
          <div className="card p-3">
            <div className="flex flex-wrap gap-1.5">
              {sources.map((source, index) => (
                <span
                  key={`${source}-${index}`}
                  className="badge gap-1 bg-slate-100 py-1 pl-2.5 pr-1 text-slate-700 dark:bg-slate-800 dark:text-slate-200"
                >
                  {source}
                  {!readOnly && (
                    <button
                      className="rounded-full p-0.5 text-slate-400 transition-colors hover:bg-slate-200 hover:text-red-500 dark:hover:bg-slate-700"
                      title={`Remove ${source}`}
                      onClick={() => setSources(sources.filter((_, i) => i !== index))}
                    >
                      <X size={11} />
                    </button>
                  )}
                </span>
              ))}
              {sources.length === 0 && (
                <span className="text-sm text-slate-400">None — the dropdown starts empty.</span>
              )}
            </div>
            {!readOnly && (
              <div className="mt-3 flex gap-2">
                <input
                  className="input"
                  placeholder="Add a source…"
                  value={newSource}
                  onChange={(e) => setNewSource(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addSource()}
                />
                <button
                  className="btn-secondary shrink-0"
                  disabled={!newSource.trim() || sources.includes(newSource.trim())}
                  onClick={addSource}
                >
                  <Plus size={14} /> Add
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {section === "roles" && (
        <div className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            The roles a new workspace starts with, and the reference data it is seeded with.
            These are read-only here — a workspace edits its own roles from its Settings, and
            changing them centrally afterwards would overwrite what a client had set up.
          </p>
          <section className="card overflow-hidden">
            <header className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/70 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/40">
              <Shield size={13} className="text-slate-400" />
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Starting roles
              </h4>
            </header>
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {(template.config.roles ?? []).map((r: any) => (
                <li key={r.name} className="flex flex-wrap items-baseline gap-x-2 px-3 py-2">
                  <span className="text-sm font-medium">{r.name}</span>
                  <span className="min-w-0 flex-1 truncate text-sm text-slate-500 dark:text-slate-400">
                    {r.description}
                  </span>
                  {(r.permissions ?? []).includes("*") && (
                    <span className="badge bg-primary-50 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">
                      full access
                    </span>
                  )}
                </li>
              ))}
              {(template.config.roles ?? []).length === 0 && (
                <li className="px-3 py-6 text-center text-sm text-slate-400">
                  None — the workspace owner would have no role to sit in.
                </li>
              )}
            </ul>
          </section>

          {template.config.masters && Object.keys(template.config.masters).length > 0 && (
            <section className="card overflow-hidden">
              <header className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/70 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/40">
                <Table2 size={13} className="text-slate-400" />
                <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Reference data
                </h4>
              </header>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {Object.entries(template.config.masters as Record<string, string[]>).map(
                  ([key, values]) => (
                    <li key={key} className="px-3 py-2">
                      <p className="text-sm font-medium capitalize">{key.replace(/_/g, " ")}</p>
                      <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
                        {values.slice(0, 8).join(" · ")}
                        {values.length > 8 && ` · +${values.length - 8} more`}
                      </p>
                    </li>
                  )
                )}
              </ul>
            </section>
          )}
        </div>
      )}

      <ConfirmDialog
        open={leaving !== null}
        onClose={() => setLeaving(null)}
        onConfirm={() => { leaving?.(); setLeaving(null); }}
        title="Leave without saving?"
        confirmLabel="Discard"
        message={`${template.name} has changes you have not saved. Leaving now loses them.`}
      />

      {!readOnly && dirty && (
        <p className="mt-6 flex items-center gap-1.5 text-xs text-slate-400">
          <Check size={12} /> Changes apply to workspaces created from here on — nothing that
          already exists is touched.
        </p>
      )}
    </div>
  );
}
