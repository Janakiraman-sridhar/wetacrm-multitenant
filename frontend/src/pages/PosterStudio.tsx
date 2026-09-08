import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertTriangle, ArrowDown, ArrowUp, Copy, Download, Image as ImageIcon, Minus,
  Plus, Send, Square, Trash2, Type, Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Modal } from "@/components/Modal";
import { PosterCanvas } from "@/components/PosterCanvas";
import { Select } from "@/components/Select";
import { useToast } from "@/context/ToastContext";
import { PosterImage, downloadPoster } from "@/components/PosterImage";
import { api, errorMessage } from "@/lib/api";
import { openWhatsApp } from "@/lib/whatsapp";

type LayerKind = "text" | "rect" | "image" | "line";

interface Layer {
  type: LayerKind;
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
  italic?: boolean;
  uppercase?: boolean;
  font?: string;
  letter_spacing?: number;
  line_height?: number;
  opacity?: number;
  shadow?: { color?: string; dx?: number; dy?: number } | null;
  outline?: { color?: string; width?: number } | null;
  radius?: number;
  max_lines?: number;
  source?: string;
  fit?: "cover" | "contain";
}

interface Background {
  color?: string;
  overlay?: string;
  image?: string;
  gradient?: { to?: string; angle?: "vertical" | "horizontal" } | null;
}

interface PosterTemplate {
  id: string;
  name: string;
  category: string;
  size: string;
  layers: Layer[];
  background: Background;
}

interface MergeInfo {
  fields: string[];
  sample: Record<string, string>;
  sizes: Record<string, { width: number; height: number }>;
  categories: string[];
  fonts: string[];
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
 *
 * A failed render is reported rather than swallowed: the last good image stays on
 * screen so the canvas does not flash empty, but the studio says so — silently
 * showing a stale poster is how "my change did nothing" happens.
 */
function usePreview(spec: object | null) {
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  const refresh = useCallback(async () => {
    if (!spec) return;
    const ticket = ++latest.current;
    setBusy(true);
    try {
      const response = await api.post("/poster/preview", spec, { responseType: "blob" });
      if (ticket !== latest.current) return; // a newer edit already won
      setError(null);
      setUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return URL.createObjectURL(response.data as Blob);
      });
    } catch (err) {
      if (ticket !== latest.current) return;
      // The body of a failed render arrives as a Blob because of responseType.
      let detail = "";
      const data = (err as any)?.response?.data;
      if (data instanceof Blob) {
        try {
          detail = JSON.parse(await data.text())?.detail ?? "";
        } catch {
          /* not JSON — fall through to the generic message */
        }
      }
      setError(detail || errorMessage(err));
    } finally {
      if (ticket === latest.current) setBusy(false);
    }
  }, [spec]);

  useEffect(() => {
    const timer = setTimeout(refresh, 250); // debounce while dragging a slider
    return () => clearTimeout(timer);
  }, [refresh]);

  return { url, busy, error };
}

const NEW_LAYERS: Record<LayerKind, Layer> = {
  text: { type: "text", x: 100, y: 400, w: 880, text: "New text", size: 48, color: "#1E293B", align: "center" },
  rect: { type: "rect", x: 100, y: 100, w: 400, h: 200, fill: "#4F46E5", radius: 16 },
  line: { type: "line", x: 100, y: 300, w: 400, h: 4, fill: "#4F46E5", radius: 2 },
  image: { type: "image", x: 100, y: 100, w: 240, h: 240, source: "logo", radius: 0, fit: "cover" },
};

const LAYER_ICONS: Record<LayerKind, typeof Type> = {
  text: Type, rect: Square, line: Minus, image: ImageIcon,
};

const FONT_LABELS: Record<string, string> = {
  sans: "Sans", serif: "Serif", mono: "Mono",
};

/** A labelled row, so the panel's forty controls line up without forty wrappers. */
function Field({ label, hint, children, className }: {
  label: string; hint?: string; children: React.ReactNode; className?: string;
}) {
  return (
    <div className={className}>
      <label className="label" title={hint}>{label}</label>
      {children}
    </div>
  );
}

function ColorInput({ value, fallback, onChange }: {
  value?: string; fallback: string; onChange: (v: string) => void;
}) {
  return (
    <input
      type="color"
      className="input h-[38px] w-full !p-1"
      value={(value ?? fallback).slice(0, 7)}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function NumberInput({ value, fallback, min, max, step, onChange }: {
  value?: number; fallback: number; min?: number; max?: number; step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <input
      type="number"
      className="input"
      value={value ?? fallback}
      min={min}
      max={max}
      step={step}
      onChange={(e) => onChange(Number(e.target.value))}
    />
  );
}

/** A 0–100 slider over a 0–1 opacity, which is the unit the renderer takes. */
function OpacityRow({ value, onChange }: { value?: number; onChange: (v: number) => void }) {
  const percent = Math.round((value ?? 1) * 100);
  return (
    <Field label={`Opacity · ${percent}%`}>
      <input
        type="range"
        min={0}
        max={100}
        value={percent}
        className="w-full accent-primary-600"
        onChange={(e) => onChange(Number(e.target.value) / 100)}
      />
    </Field>
  );
}

function Toggle({ checked, onChange, children }: {
  checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode;
}) {
  return (
    <label className="flex cursor-pointer select-none items-center gap-2 text-sm">
      <input
        type="checkbox"
        className="h-4 w-4 accent-primary-600"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      {children}
    </label>
  );
}

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
  const { url: previewUrl, busy, error: previewError } = usePreview(spec);

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

  const patchLayer = useCallback((index: number, patch: Partial<Layer>) => {
    setDraft((current) =>
      current
        ? { ...current, layers: current.layers.map((l, i) => (i === index ? { ...l, ...patch } : l)) }
        : current
    );
  }, []);

  const patchBackground = (patch: Partial<Background>) =>
    draft && setDraft({ ...draft, background: { ...draft.background, ...patch } });

  const moveLayer = (index: number, delta: number) => {
    if (!draft) return;
    const target = index + delta;
    if (target < 0 || target >= draft.layers.length) return;
    const layers = [...draft.layers];
    [layers[index], layers[target]] = [layers[target], layers[index]];
    setDraft({ ...draft, layers });
    setActiveLayer(target);
  };

  const addLayer = (kind: LayerKind) => {
    if (!draft) return;
    setDraft({ ...draft, layers: [...draft.layers, { ...NEW_LAYERS[kind] }] });
    setActiveLayer(draft.layers.length);
  };

  const duplicateLayer = (index: number) => {
    if (!draft) return;
    const copy = structuredClone(draft.layers[index]);
    copy.y = (copy.y ?? 0) + 40;
    const layers = [...draft.layers];
    layers.splice(index + 1, 0, copy);
    setDraft({ ...draft, layers });
    setActiveLayer(index + 1);
  };

  if (!draft) return <p className="text-slate-400">Loading the studio…</p>;

  const dims = merge?.sizes?.[draft.size] ?? { width: 1080, height: 1080 };
  const layer = activeLayer !== null ? draft.layers[activeLayer] : null;
  const fonts = merge?.fonts ?? ["sans"];

  /** Every layer takes the same geometry, so it is one block rather than four. */
  const geometry = (index: number, l: Layer) => (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Field label="X"><NumberInput value={l.x} fallback={0} onChange={(v) => patchLayer(index, { x: v })} /></Field>
      <Field label="Y"><NumberInput value={l.y} fallback={0} onChange={(v) => patchLayer(index, { y: v })} /></Field>
      <Field
        label={l.type === "text" ? "Wrap width" : "Width"}
        hint={l.type === "text" ? "Text wraps inside this width" : undefined}
      >
        <NumberInput value={l.w} fallback={l.type === "text" ? dims.width - l.x : 100}
                     onChange={(v) => patchLayer(index, { w: v })} />
      </Field>
      {/* No height for text: the renderer derives it from the wrapped lines, so a
          height box here would be a control that does nothing. */}
      {l.type === "text" ? (
        <Field label="Line height">
          <NumberInput value={l.line_height} fallback={1.25} step={0.05} min={0.8}
                       onChange={(v) => patchLayer(index, { line_height: v })} />
        </Field>
      ) : (
        <Field label={l.type === "line" ? "Thickness" : "Height"}>
          <NumberInput value={l.h} fallback={100} min={1}
                       onChange={(v) => patchLayer(index, { h: v })} />
        </Field>
      )}
    </div>
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Poster Studio</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Drag anything on the poster to move it. The preview is rendered by the same code
            that produces the file your customer receives.
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

      {previewError && (
        <p className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>
            The preview could not be rendered, so the poster below is the last one that worked.{" "}
            {previewError}
          </span>
        </p>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="card flex min-h-0 items-center justify-center overflow-auto p-4">
          <PosterCanvas
            url={previewUrl}
            busy={busy}
            width={dims.width}
            height={dims.height}
            layers={draft.layers}
            activeLayer={activeLayer}
            maxWidth={draft.size === "story" ? 320 : 460}
            onSelect={setActiveLayer}
            onPatch={patchLayer}
          />
        </div>

        {/* editor */}
        <div className="card flex min-h-0 flex-col gap-4 overflow-y-auto p-4">
          <div className="space-y-3">
            <Field label="Design name">
              <input className="input" value={draft.name}
                     onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Size">
                <Select
                  value={draft.size}
                  onChange={(v) => setDraft({ ...draft, size: v })}
                  options={Object.entries(merge?.sizes ?? {}).map(([key, d]) => ({
                    value: key, label: `${key} (${d.width}×${d.height})`,
                  }))}
                />
              </Field>
              <Field label="Category">
                <Select
                  value={draft.category}
                  onChange={(v) => setDraft({ ...draft, category: v })}
                  options={(merge?.categories ?? [draft.category]).map((c) => ({ value: c, label: c }))}
                />
              </Field>
            </div>

            <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Background
              </p>
              <Field label="Colour">
                <ColorInput value={draft.background?.color} fallback="#FFFFFF"
                            onChange={(v) => patchBackground({ color: v })} />
              </Field>
              {/* Behind a toggle rather than an always-present swatch: a colour box
                  showing a default reads as a gradient that is already applied. */}
              <div className="mt-2">
                <Toggle
                  checked={!!draft.background?.gradient?.to}
                  onChange={(v) => patchBackground({
                    gradient: v ? { to: "#4F46E5", angle: "vertical" } : null,
                  })}
                >
                  Fade into a second colour
                </Toggle>
              </div>
              {draft.background?.gradient?.to && (
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <Field label="Fade to">
                    <ColorInput value={draft.background.gradient.to} fallback="#4F46E5"
                                onChange={(v) => patchBackground({
                                  gradient: { ...draft.background.gradient, to: v },
                                })} />
                  </Field>
                  <Field label="Direction">
                    <Select
                      value={draft.background.gradient.angle ?? "vertical"}
                      onChange={(v) => patchBackground({
                        gradient: { ...draft.background.gradient, angle: v as "vertical" | "horizontal" },
                      })}
                      options={[
                        { value: "vertical", label: "Top to bottom" },
                        { value: "horizontal", label: "Left to right" },
                      ]}
                    />
                  </Field>
                </div>
              )}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between pb-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Layers · drawn bottom to top
              </p>
              <div className="flex gap-1">
                {(Object.keys(NEW_LAYERS) as LayerKind[]).map((kind) => {
                  const Icon = LAYER_ICONS[kind];
                  return (
                    <button key={kind} className="btn-ghost !p-1.5" title={`Add ${kind}`}
                            onClick={() => addLayer(kind)}>
                      <Icon size={15} />
                    </button>
                  );
                })}
              </div>
            </div>

            <ul className="space-y-1">
              {draft.layers.map((l, index) => {
                const Icon = LAYER_ICONS[l.type] ?? Square;
                return (
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
                    <Icon size={13} className="shrink-0" />
                    <span className="min-w-0 flex-1 truncate">
                      {l.type === "text" ? l.text : l.type === "image" ? l.source : l.type}
                    </span>
                    <button className="btn-ghost !p-1" title="Move down a layer"
                            onClick={(e) => { e.stopPropagation(); moveLayer(index, -1); }}>
                      <ArrowUp size={12} />
                    </button>
                    <button className="btn-ghost !p-1" title="Move up a layer"
                            onClick={(e) => { e.stopPropagation(); moveLayer(index, 1); }}>
                      <ArrowDown size={12} />
                    </button>
                    <button className="btn-ghost !p-1" title="Duplicate"
                            onClick={(e) => { e.stopPropagation(); duplicateLayer(index); }}>
                      <Copy size={12} />
                    </button>
                    <button
                      className="btn-ghost !p-1 text-red-500"
                      title="Delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDraft({ ...draft, layers: draft.layers.filter((_, i) => i !== index) });
                        setActiveLayer(null);
                      }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </li>
                );
              })}
              {draft.layers.length === 0 && (
                <li className="rounded-lg border border-dashed border-slate-200 py-6 text-center text-sm text-slate-400 dark:border-slate-700">
                  Empty design — add a layer above.
                </li>
              )}
            </ul>
          </div>

          {layer && activeLayer !== null && (
            <div className="space-y-3 border-t border-slate-100 pt-4 dark:border-slate-800">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
                {layer.type} layer
              </p>

              {layer.type === "text" && (
                <>
                  <Field label="Text">
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
                          className="badge bg-slate-100 text-[10px] hover:bg-primary-100 dark:bg-slate-800 dark:hover:bg-primary-900/50"
                          title={`Insert {${field}} — previews as "${merge?.sample[field] ?? ""}"`}
                          onClick={() => patchLayer(activeLayer, { text: `${layer.text ?? ""}{${field}}` })}
                        >
                          {`{${field}}`}
                        </button>
                      ))}
                    </div>
                  </Field>

                  <div className="grid grid-cols-3 gap-2">
                    <Field label="Size">
                      <NumberInput value={layer.size} fallback={40} min={1}
                                   onChange={(v) => patchLayer(activeLayer, { size: v })} />
                    </Field>
                    <Field label="Colour">
                      <ColorInput value={layer.color} fallback="#111827"
                                  onChange={(v) => patchLayer(activeLayer, { color: v })} />
                    </Field>
                    <Field label="Align">
                      <Select
                        value={layer.align ?? "left"}
                        onChange={(v) => patchLayer(activeLayer, { align: v as Layer["align"] })}
                        options={[
                          { value: "left", label: "Left" },
                          { value: "center", label: "Center" },
                          { value: "right", label: "Right" },
                        ]}
                      />
                    </Field>
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <Field label="Font">
                      <Select
                        value={layer.font ?? "sans"}
                        onChange={(v) => patchLayer(activeLayer, { font: v })}
                        options={fonts.map((f) => ({ value: f, label: FONT_LABELS[f] ?? f }))}
                      />
                    </Field>
                    <Field label="Spacing" hint="Extra space between letters">
                      <NumberInput value={layer.letter_spacing} fallback={0} step={0.5}
                                   onChange={(v) => patchLayer(activeLayer, { letter_spacing: v })} />
                    </Field>
                    <Field label="Max lines" hint="Longer text is trimmed with an ellipsis">
                      <NumberInput value={layer.max_lines} fallback={4} min={1}
                                   onChange={(v) => patchLayer(activeLayer, { max_lines: v })} />
                    </Field>
                  </div>

                  <div className="flex flex-wrap gap-x-4 gap-y-2">
                    <Toggle checked={!!layer.bold} onChange={(v) => patchLayer(activeLayer, { bold: v })}>
                      Bold
                    </Toggle>
                    <Toggle checked={!!layer.italic} onChange={(v) => patchLayer(activeLayer, { italic: v })}>
                      Italic
                    </Toggle>
                    <Toggle checked={!!layer.uppercase} onChange={(v) => patchLayer(activeLayer, { uppercase: v })}>
                      UPPERCASE
                    </Toggle>
                  </div>

                  {/* Shadow and outline earn their space on a poster: the text is
                      routinely read over a photo, where plain colour disappears. */}
                  <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                    <Toggle
                      checked={!!layer.shadow?.color}
                      onChange={(v) => patchLayer(activeLayer, {
                        shadow: v ? { color: "#000000", dx: 2, dy: 2 } : null,
                      })}
                    >
                      Drop shadow
                    </Toggle>
                    {layer.shadow?.color && (
                      <div className="mt-2 grid grid-cols-3 gap-2">
                        <Field label="Colour">
                          <ColorInput value={layer.shadow.color} fallback="#000000"
                                      onChange={(v) => patchLayer(activeLayer, {
                                        shadow: { ...layer.shadow, color: v },
                                      })} />
                        </Field>
                        <Field label="Right">
                          <NumberInput value={layer.shadow.dx} fallback={2}
                                       onChange={(v) => patchLayer(activeLayer, {
                                         shadow: { ...layer.shadow, dx: v },
                                       })} />
                        </Field>
                        <Field label="Down">
                          <NumberInput value={layer.shadow.dy} fallback={2}
                                       onChange={(v) => patchLayer(activeLayer, {
                                         shadow: { ...layer.shadow, dy: v },
                                       })} />
                        </Field>
                      </div>
                    )}
                  </div>

                  <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                    <Toggle
                      checked={!!layer.outline?.width}
                      onChange={(v) => patchLayer(activeLayer, {
                        outline: v ? { color: "#000000", width: 2 } : null,
                      })}
                    >
                      Outline
                    </Toggle>
                    {!!layer.outline?.width && (
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        <Field label="Colour">
                          <ColorInput value={layer.outline.color} fallback="#000000"
                                      onChange={(v) => patchLayer(activeLayer, {
                                        outline: { ...layer.outline, color: v },
                                      })} />
                        </Field>
                        <Field label="Thickness">
                          <NumberInput value={layer.outline.width} fallback={2} min={1} max={8}
                                       onChange={(v) => patchLayer(activeLayer, {
                                         outline: { ...layer.outline, width: v },
                                       })} />
                        </Field>
                      </div>
                    )}
                  </div>
                </>
              )}

              {(layer.type === "rect" || layer.type === "line") && (
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Fill">
                    <ColorInput value={layer.fill} fallback="#4F46E5"
                                onChange={(v) => patchLayer(activeLayer, { fill: v })} />
                  </Field>
                  <Field label="Corner radius">
                    <NumberInput value={layer.radius} fallback={0} min={0}
                                 onChange={(v) => patchLayer(activeLayer, { radius: v })} />
                  </Field>
                </div>
              )}

              {layer.type === "image" && (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="Source">
                      <Select
                        value={layer.source ?? "logo"}
                        onChange={(v) => patchLayer(activeLayer, { source: v })}
                        options={[{ value: "logo", label: "Workspace logo" }]}
                      />
                    </Field>
                    <Field label="Fit" hint="Cover fills the box and crops; contain fits it all in">
                      <Select
                        value={layer.fit ?? "cover"}
                        onChange={(v) => patchLayer(activeLayer, { fit: v as Layer["fit"] })}
                        options={[
                          { value: "cover", label: "Cover (crop)" },
                          { value: "contain", label: "Contain (fit)" },
                        ]}
                      />
                    </Field>
                  </div>
                  <Field label="Corner radius">
                    <NumberInput value={layer.radius} fallback={0} min={0}
                                 onChange={(v) => patchLayer(activeLayer, { radius: v })} />
                  </Field>
                  <p className="text-xs text-slate-400">
                    Set the logo in Settings → Company. More sources arrive with the asset library.
                  </p>
                </>
              )}

              <OpacityRow value={layer.opacity} onChange={(v) => patchLayer(activeLayer, { opacity: v })} />
              {geometry(activeLayer, layer)}
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
                            onClick={() => openWhatsApp(item.phone, `Dear ${item.name},`)}
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
                  <Plus size={14} /> Generate another
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
