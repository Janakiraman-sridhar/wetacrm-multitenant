import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowDown, ArrowUp, Copy, Download, Image as ImageIcon, Loader2, Plus, Send,
  Square, Trash2, Type, Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Modal } from "@/components/Modal";
import { Select } from "@/components/Select";
import { useToast } from "@/context/ToastContext";
import { PosterImage, downloadPoster } from "@/components/PosterImage";
import { api, errorMessage } from "@/lib/api";
import { openWhatsApp } from "@/lib/whatsapp";

interface Layer {
  type: "text" | "rect" | "image";
  x: number;
  y: number;
  w?: number;
  h?: number;
  text?: string;
  size?: number;
  color?: string;
  fill?: string;
  align?: "left" | "center" | "right";
  bold?: boolean;
  radius?: number;
  max_lines?: number;
  source?: string;
}

interface PosterTemplate {
  id: string;
  name: string;
  category: string;
  size: string;
  layers: Layer[];
  background: { color?: string; overlay?: string; image?: string };
}

interface MergeInfo {
  fields: string[];
  sample: Record<string, string>;
  sizes: Record<string, { width: number; height: number }>;
  categories: string[];
}

interface BatchItem {
  contact_id: string;
  name: string;
  phone: string | null;
  file_key?: string;
  error?: string;
}

/**
 * Render a design through the server.
 *
 * The editor previews with the *same* renderer that produces the file a customer
 * receives, so what an agent designs is what gets sent. A separate client-side
 * preview would drift the first time a font fell back or a line wrapped differently.
 */
function usePreview(spec: object | null) {
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const latest = useRef(0);

  const refresh = useCallback(async () => {
    if (!spec) return;
    const ticket = ++latest.current;
    setBusy(true);
    try {
      const response = await api.post("/poster/preview", spec, { responseType: "blob" });
      if (ticket !== latest.current) return; // a newer edit already won
      setUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return URL.createObjectURL(response.data as Blob);
      });
    } catch {
      /* leave the last good preview on screen rather than blanking it */
    } finally {
      if (ticket === latest.current) setBusy(false);
    }
  }, [spec]);

  useEffect(() => {
    const timer = setTimeout(refresh, 350); // debounce while dragging a slider
    return () => clearTimeout(timer);
  }, [refresh]);

  return { url, busy };
}

const NEW_LAYERS: Record<string, Layer> = {
  text: { type: "text", x: 100, y: 400, w: 880, text: "New text", size: 48, color: "#1E293B", align: "center" },
  rect: { type: "rect", x: 100, y: 100, w: 400, h: 200, fill: "#4F46E5", radius: 16 },
  image: { type: "image", x: 100, y: 100, w: 240, h: 240, source: "logo", radius: 0 },
};

export default function PosterStudio() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<PosterTemplate | null>(null);
  const [activeLayer, setActiveLayer] = useState<number | null>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [audience, setAudience] = useState<"birthdays" | "renewals">("birthdays");
  const [withinDays, setWithinDays] = useState(7);
  const [batchResult, setBatchResult] = useState<BatchItem[] | null>(null);

  const { data: templates } = useQuery({
    queryKey: ["poster-templates"],
    queryFn: async () => (await api.get<PosterTemplate[]>("/poster/templates")).data,
  });
  const { data: merge } = useQuery({
    queryKey: ["poster-merge-fields"],
    queryFn: async () => (await api.get<MergeInfo>("/poster/merge-fields")).data,
  });
  const { data: waStatus } = useQuery({
    queryKey: ["whatsapp-status"],
    queryFn: async () => (await api.get("/whatsapp/status")).data,
  });

  useEffect(() => {
    if (!draft && templates?.length) {
      setSelectedId(templates[0].id);
      setDraft(structuredClone(templates[0]));
    }
  }, [templates, draft]);

  const spec = useMemo(
    () => (draft ? { size: draft.size, layers: draft.layers, background: draft.background } : null),
    [draft]
  );
  const { url: previewUrl, busy } = usePreview(spec);

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.patch(`/poster/templates/${draft!.id}`, {
          name: draft!.name, category: draft!.category, size: draft!.size,
          layers: draft!.layers, background: draft!.background,
        })
      ).data,
    onSuccess: () => {
      toast("Design saved");
      queryClient.invalidateQueries({ queryKey: ["poster-templates"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const generate = useMutation({
    mutationFn: async () =>
      (
        await api.post("/poster/batches", {
          template_id: draft!.id, audience, within_days: withinDays,
        })
      ).data,
    onSuccess: (data) => {
      setBatchResult(data.items);
      toast(`${data.items.length} poster(s) generated`);
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const { data: audienceList } = useQuery({
    queryKey: ["poster-audience", audience, withinDays],
    queryFn: async () =>
      (await api.get("/poster/audience", { params: { kind: audience, within_days: withinDays } })).data,
    enabled: batchOpen,
  });

  const patchLayer = (index: number, patch: Partial<Layer>) => {
    if (!draft) return;
    const layers = draft.layers.map((l, i) => (i === index ? { ...l, ...patch } : l));
    setDraft({ ...draft, layers });
  };

  const moveLayer = (index: number, delta: number) => {
    if (!draft) return;
    const target = index + delta;
    if (target < 0 || target >= draft.layers.length) return;
    const layers = [...draft.layers];
    [layers[index], layers[target]] = [layers[target], layers[index]];
    setDraft({ ...draft, layers });
    setActiveLayer(target);
  };

  if (!draft) return <p className="text-slate-400">Loading the studio…</p>;

  const layer = activeLayer !== null ? draft.layers[activeLayer] : null;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Poster Studio</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Design once, send personalised to everyone. The preview is rendered by the same
            code that produces the file your customer receives.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={selectedId ?? ""}
            onChange={(id) => {
              const found = templates?.find((t) => t.id === id);
              if (found) {
                setSelectedId(id);
                setDraft(structuredClone(found));
                setActiveLayer(null);
              }
            }}
            options={(templates ?? []).map((t) => ({ value: t.id, label: t.name }))}
          />
          <button className="btn-secondary" onClick={() => setBatchOpen(true)}>
            <Users size={15} /> Generate for…
          </button>
          <button className="btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save design"}
          </button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        {/* preview */}
        <div className="card flex min-h-0 items-center justify-center overflow-auto p-4">
          {previewUrl ? (
            <img
              src={previewUrl}
              alt="Poster preview"
              className={clsx(
                "max-h-full w-auto rounded-lg shadow-lg transition-opacity",
                busy && "opacity-60"
              )}
              style={{ maxWidth: draft.size === "story" ? 320 : 460 }}
            />
          ) : (
            <span className="flex items-center gap-2 text-slate-400">
              <Loader2 size={16} className="animate-spin" /> Rendering…
            </span>
          )}
        </div>

        {/* editor */}
        <div className="card flex min-h-0 flex-col overflow-y-auto p-4">
          <div className="space-y-3 border-b border-slate-100 pb-4 dark:border-slate-800">
            <div>
              <label className="label">Design name</label>
              <input
                className="input"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Size</label>
                <Select
                  value={draft.size}
                  onChange={(v) => setDraft({ ...draft, size: v })}
                  options={Object.entries(merge?.sizes ?? {}).map(([key, dims]) => ({
                    value: key, label: `${key} (${dims.width}×${dims.height})`,
                  }))}
                />
              </div>
              <div>
                <label className="label">Background</label>
                <input
                  type="color"
                  className="input !p-1 h-[38px]"
                  value={draft.background?.color ?? "#FFFFFF"}
                  onChange={(e) =>
                    setDraft({ ...draft, background: { ...draft.background, color: e.target.value } })
                  }
                />
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between py-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Layers · drawn bottom to top
            </p>
            <div className="flex gap-1">
              {([["text", Type], ["rect", Square], ["image", ImageIcon]] as const).map(([kind, Icon]) => (
                <button
                  key={kind}
                  className="btn-ghost !p-1.5"
                  title={`Add ${kind}`}
                  onClick={() => {
                    setDraft({ ...draft, layers: [...draft.layers, { ...NEW_LAYERS[kind] }] });
                    setActiveLayer(draft.layers.length);
                  }}
                >
                  <Icon size={15} />
                </button>
              ))}
            </div>
          </div>

          <ul className="space-y-1">
            {draft.layers.map((l, index) => (
              <li
                key={index}
                className={clsx(
                  "flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors",
                  activeLayer === index
                    ? "bg-primary-50 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300"
                    : "hover:bg-slate-50 dark:hover:bg-slate-800/60"
                )}
                onClick={() => setActiveLayer(index)}
              >
                {l.type === "text" ? <Type size={13} /> : l.type === "rect" ? <Square size={13} /> : <ImageIcon size={13} />}
                <span className="min-w-0 flex-1 truncate">
                  {l.type === "text" ? l.text : l.type === "image" ? l.source : "Shape"}
                </span>
                <button className="btn-ghost !p-1" onClick={(e) => { e.stopPropagation(); moveLayer(index, -1); }}>
                  <ArrowUp size={12} />
                </button>
                <button className="btn-ghost !p-1" onClick={(e) => { e.stopPropagation(); moveLayer(index, 1); }}>
                  <ArrowDown size={12} />
                </button>
                <button
                  className="btn-ghost !p-1 text-red-500"
                  onClick={(e) => {
                    e.stopPropagation();
                    setDraft({ ...draft, layers: draft.layers.filter((_, i) => i !== index) });
                    setActiveLayer(null);
                  }}
                >
                  <Trash2 size={12} />
                </button>
              </li>
            ))}
          </ul>

          {layer && activeLayer !== null && (
            <div className="mt-4 space-y-3 border-t border-slate-100 pt-4 dark:border-slate-800">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
                Selected layer
              </p>

              {layer.type === "text" && (
                <>
                  <div>
                    <label className="label">Text</label>
                    <textarea
                      className="input"
                      rows={2}
                      value={layer.text ?? ""}
                      onChange={(e) => patchLayer(activeLayer, { text: e.target.value })}
                    />
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {(merge?.fields ?? []).map((field) => (
                        <button
                          key={field}
                          className="badge bg-slate-100 text-[10px] hover:bg-primary-100 dark:bg-slate-800"
                          title={`Insert {${field}} — previews as "${merge?.sample[field] ?? ""}"`}
                          onClick={() =>
                            patchLayer(activeLayer, { text: `${layer.text ?? ""}{${field}}` })
                          }
                        >
                          {`{${field}}`}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <label className="label">Size</label>
                      <input type="number" className="input" value={layer.size ?? 40}
                             onChange={(e) => patchLayer(activeLayer, { size: Number(e.target.value) })} />
                    </div>
                    <div>
                      <label className="label">Colour</label>
                      <input type="color" className="input !p-1 h-[38px]" value={layer.color ?? "#000000"}
                             onChange={(e) => patchLayer(activeLayer, { color: e.target.value })} />
                    </div>
                    <div>
                      <label className="label">Align</label>
                      <Select
                        value={layer.align ?? "left"}
                        onChange={(v) => patchLayer(activeLayer, { align: v as Layer["align"] })}
                        options={[
                          { value: "left", label: "Left" },
                          { value: "center", label: "Center" },
                          { value: "right", label: "Right" },
                        ]}
                      />
                    </div>
                  </div>
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input type="checkbox" className="h-4 w-4 accent-primary-600"
                           checked={!!layer.bold}
                           onChange={(e) => patchLayer(activeLayer, { bold: e.target.checked })} />
                    Bold
                  </label>
                </>
              )}

              {layer.type === "rect" && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="label">Fill</label>
                    <input type="color" className="input !p-1 h-[38px]" value={layer.fill ?? "#4F46E5"}
                           onChange={(e) => patchLayer(activeLayer, { fill: e.target.value })} />
                  </div>
                  <div>
                    <label className="label">Corner radius</label>
                    <input type="number" className="input" value={layer.radius ?? 0}
                           onChange={(e) => patchLayer(activeLayer, { radius: Number(e.target.value) })} />
                  </div>
                </div>
              )}

              {layer.type === "image" && (
                <div>
                  <label className="label">Source</label>
                  <Select
                    value={layer.source ?? "logo"}
                    onChange={(v) => patchLayer(activeLayer, { source: v })}
                    options={[{ value: "logo", label: "Workspace logo" }]}
                  />
                  <p className="mt-1 text-xs text-slate-400">
                    Set the logo in Settings → Company. More sources arrive with the asset library.
                  </p>
                </div>
              )}

              <div className="grid grid-cols-4 gap-2">
                {(["x", "y", "w", "h"] as const).map((axis) => (
                  <div key={axis}>
                    <label className="label uppercase">{axis}</label>
                    <input
                      type="number"
                      className="input"
                      value={(layer as any)[axis] ?? 0}
                      onChange={(e) => patchLayer(activeLayer, { [axis]: Number(e.target.value) } as any)}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* batch */}
      <Modal open={batchOpen} onClose={() => { setBatchOpen(false); setBatchResult(null); }}
             title="Generate personalised posters" wide>
        <div className="space-y-4">
          {!batchResult && (
            <>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="label">Send to</label>
                  <Select
                    value={audience}
                    onChange={(v) => setAudience(v as "birthdays" | "renewals")}
                    options={[
                      { value: "birthdays", label: "Customers with a birthday coming up" },
                      { value: "renewals", label: "Policies due for renewal" },
                    ]}
                  />
                </div>
                <div>
                  <label className="label">Within the next</label>
                  <Select
                    value={String(withinDays)}
                    onChange={(v) => setWithinDays(Number(v))}
                    options={[1, 7, 15, 30, 60].map((d) => ({ value: String(d), label: `${d} days` }))}
                  />
                </div>
              </div>

              <div className="card max-h-56 overflow-y-auto p-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                  {(audienceList ?? []).length} recipient(s)
                </p>
                <ul className="space-y-1 text-sm">
                  {(audienceList ?? []).map((p: any) => (
                    <li key={p.contact_id} className="flex justify-between">
                      <span>{p.name}</span>
                      <span className="text-slate-400">{p.phone ?? "no number"}</span>
                    </li>
                  ))}
                  {(audienceList ?? []).length === 0 && (
                    <li className="py-4 text-center text-slate-400">Nobody matches this yet.</li>
                  )}
                </ul>
              </div>

              <div className="flex justify-end gap-2">
                <button className="btn-secondary" onClick={() => setBatchOpen(false)}>Cancel</button>
                <button
                  className="btn-primary"
                  disabled={generate.isPending || (audienceList ?? []).length === 0}
                  onClick={() => generate.mutate()}
                >
                  {generate.isPending ? "Generating…" : `Generate ${(audienceList ?? []).length} poster(s)`}
                </button>
              </div>
            </>
          )}

          {batchResult && (
            <>
              {!waStatus?.can_send_from_server && (
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                  The WhatsApp API is not set up for this workspace, so each poster opens in your own
                  WhatsApp with the message ready — you press send. Download the image and attach it.
                </p>
              )}
              <div className="grid max-h-[26rem] grid-cols-2 gap-3 overflow-y-auto sm:grid-cols-3">
                {batchResult.map((item) => (
                  <div key={item.contact_id} className="card overflow-hidden">
                    {item.file_key ? (
                      <PosterImage fileKey={item.file_key} alt={item.name} className="w-full" />
                    ) : (
                      <div className="grid h-32 place-items-center text-xs text-red-500">
                        {item.error ?? "Failed"}
                      </div>
                    )}
                    <div className="p-2">
                      <p className="truncate text-sm font-medium">{item.name}</p>
                      <p className="truncate text-xs text-slate-400">{item.phone ?? "no number"}</p>
                      <div className="mt-1.5 flex gap-1">
                        {item.file_key && (
                          <button
                            className="btn-secondary !px-2 !py-1 text-xs"
                            title="Download this poster"
                            onClick={() => downloadPoster(item.file_key!, `${item.name}.png`)}
                          >
                            <Download size={12} />
                          </button>
                        )}
                        {item.phone && (
                          <button
                            className="btn-secondary !px-2 !py-1 text-xs text-emerald-600"
                            title="Open WhatsApp with the message ready"
                            onClick={() =>
                              openWhatsApp(item.phone, `Dear ${item.name},`)
                            }
                          >
                            <Send size={12} />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex justify-end gap-2">
                <button className="btn-secondary" onClick={() => setBatchResult(null)}>
                  <Copy size={14} /> Generate another
                </button>
                <button className="btn-primary" onClick={() => { setBatchOpen(false); setBatchResult(null); }}>
                  Done
                </button>
              </div>
            </>
          )}
        </div>
      </Modal>
    </div>
  );
}
