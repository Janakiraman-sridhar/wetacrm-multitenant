import clsx from "clsx";
import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

export interface CanvasLayer {
  type: string;
  x: number;
  y: number;
  w?: number;
  h?: number;
  size?: number;
  line_height?: number;
  text?: string;
}

/** The canvas only ever moves and resizes — it never touches a layer's styling. */
export type GeometryPatch = { x?: number; y?: number; w?: number; h?: number };

type Handle = "move" | "e" | "s" | "se";

/**
 * A grab point. The visible dot is small so it does not hide the design; the
 * element around it is 20px, because a handle you have to hit within three pixels
 * is one you miss — and a miss lands on the box underneath and drags *that*.
 */
function Handle({ index, handle, className, title, start }: {
  index: number;
  handle: Handle;
  className?: string;
  title: string;
  start: (i: number, h: Handle) => (e: React.PointerEvent) => void;
}) {
  return (
    <span
      onPointerDown={start(index, handle)}
      title={title}
      className={clsx("absolute grid h-5 w-5 place-items-center", className)}
    >
      <span className="h-2.5 w-2.5 rounded-full border border-white bg-primary-500 shadow" />
    </span>
  );
}

/**
 * The preview, with the layers draggable on top of it.
 *
 * The poster itself is rendered by the server — that is deliberate and stays that
 * way, because the editor must show exactly what the customer receives. What was
 * missing is that positioning a layer meant typing numbers into x/y/w and guessing:
 * you changed a value, the element jumped somewhere unexpected, and it read as
 * "nothing happened". So this overlays an invisible, interactive box per layer on
 * the rendered image and lets an agent drag it.
 *
 * The boxes are geometry only — no text, no colour, nothing drawn twice. Drawing a
 * second, client-side copy of the design is exactly the drift the server-rendered
 * preview exists to prevent.
 *
 * A text layer's height is not in the spec: the renderer derives it from wrapping.
 * The box therefore shows an estimate from the font size and line height, and only
 * its width is resizable — offering a height handle that silently does nothing is
 * the bug this component was written to fix, not one to reintroduce.
 */
export function PosterCanvas({
  url,
  busy,
  width,
  height,
  layers,
  activeLayer,
  maxWidth,
  onSelect,
  onPatch,
  onCommit,
  editable = true,
}: {
  url: string | null;
  busy: boolean;
  /** Poster pixel dimensions, e.g. 1080×1080. */
  width: number;
  height: number;
  layers: CanvasLayer[];
  activeLayer: number | null;
  maxWidth: number;
  onSelect: (index: number | null) => void;
  onPatch: (index: number, patch: GeometryPatch) => void;
  /** Fired once when a drag ends, so history can record one step, not sixty. */
  onCommit?: () => void;
  editable?: boolean;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ width: 0, height: 0 });
  const drag = useRef<{
    index: number;
    handle: Handle;
    startX: number;
    startY: number;
    origin: CanvasLayer;
  } | null>(null);

  // The overlay has to track the rendered image exactly, and the image is sized by
  // the layout rather than by us.
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const measure = () =>
      setBox({ width: frame.clientWidth, height: frame.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(frame);
    return () => observer.disconnect();
  }, [url, maxWidth]);

  const scale = box.width ? box.width / width : 0;

  const onPointerMove = useCallback(
    (event: PointerEvent) => {
      const state = drag.current;
      if (!state || !scale) return;
      const dx = (event.clientX - state.startX) / scale;
      const dy = (event.clientY - state.startY) / scale;
      const { index, handle, origin } = state;

      if (handle === "move") {
        onPatch(index, {
          x: Math.round(origin.x + dx),
          y: Math.round(origin.y + dy),
        });
        return;
      }
      const patch: GeometryPatch = {};
      if (handle === "e" || handle === "se") {
        patch.w = Math.max(16, Math.round((origin.w ?? 100) + dx));
      }
      if (handle === "s" || handle === "se") {
        patch.h = Math.max(4, Math.round((origin.h ?? 100) + dy));
      }
      onPatch(index, patch);
    },
    [onPatch, scale]
  );

  const endDrag = useCallback(() => {
    if (drag.current) {
      drag.current = null;
      onCommit?.();
    }
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", endDrag);
  }, [onPointerMove, onCommit]);

  useEffect(() => () => endDrag(), [endDrag]);

  const startDrag = (index: number, handle: Handle) => (event: React.PointerEvent) => {
    if (!editable) return;
    event.preventDefault();
    event.stopPropagation();
    onSelect(index);
    drag.current = {
      index,
      handle,
      startX: event.clientX,
      startY: event.clientY,
      origin: { ...layers[index] },
    };
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", endDrag);
  };

  /** A text layer's height is derived by the renderer; estimate it for the box. */
  const boxHeight = (layer: CanvasLayer) => {
    if (layer.type === "text") {
      const size = layer.size ?? 40;
      return Math.round(size * (layer.line_height ?? 1.25) * 1.1);
    }
    return layer.h ?? 100;
  };

  return (
    <div className="flex h-full w-full items-center justify-center">
      <div
        ref={frameRef}
        className="relative"
        style={{ maxWidth, width: "100%", aspectRatio: `${width} / ${height}` }}
        onPointerDown={() => editable && onSelect(null)}
      >
        {url ? (
          <img
            src={url}
            alt="Poster preview"
            draggable={false}
            className={clsx(
              "h-full w-full select-none rounded-lg object-contain shadow-lg transition-opacity",
              busy && "opacity-70"
            )}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center rounded-lg border border-dashed border-slate-300 dark:border-slate-700">
            <span className="flex items-center gap-2 text-sm text-slate-400">
              <Loader2 size={16} className="animate-spin" /> Rendering…
            </span>
          </div>
        )}

        {busy && url && (
          <span className="absolute right-2 top-2 flex items-center gap-1.5 rounded-full bg-slate-900/70 px-2 py-1 text-[11px] font-medium text-white">
            <Loader2 size={11} className="animate-spin" /> updating
          </span>
        )}

        {editable && scale > 0 && layers.map((layer, index) => {
          const selected = index === activeLayer;
          const w = layer.type === "text" ? layer.w ?? width : layer.w ?? 100;
          return (
            <div
              key={index}
              onPointerDown={startDrag(index, "move")}
              className={clsx(
                "absolute cursor-move rounded-sm transition-colors",
                selected
                  ? "ring-2 ring-primary-500"
                  : "ring-1 ring-transparent hover:ring-1 hover:ring-primary-400/60"
              )}
              style={{
                left: layer.x * scale,
                top: layer.y * scale,
                width: Math.max(8, w * scale),
                height: Math.max(8, boxHeight(layer) * scale),
              }}
              title={layer.type === "text" ? layer.text : layer.type}
            >
              {selected && (
                <>
                  {/* Width: every layer type has one the renderer honours. */}
                  <Handle index={index} handle="e" start={startDrag}
                          className="-right-2.5 top-1/2 -translate-y-1/2 cursor-ew-resize"
                          title="Drag to change the width" />
                  {/* Height only where it is real — see the note above. */}
                  {layer.type !== "text" && (
                    <>
                      <Handle index={index} handle="s" start={startDrag}
                              className="-bottom-2.5 left-1/2 -translate-x-1/2 cursor-ns-resize"
                              title="Drag to change the height" />
                      <Handle index={index} handle="se" start={startDrag}
                              className="-bottom-2.5 -right-2.5 cursor-nwse-resize"
                              title="Drag to resize" />
                    </>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
