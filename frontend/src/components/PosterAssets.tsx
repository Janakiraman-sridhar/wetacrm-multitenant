import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, ImagePlus, Loader2, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { Modal } from "@/components/Modal";
import { useAuthedImage } from "@/components/PosterImage";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";

export interface PosterAsset {
  id: string;
  name: string;
  mime_type: string;
  width: number;
  height: number;
  size_bytes: number;
}

/** The workspace's uploaded poster images. Cached, because the picker reopens a lot. */
export function usePosterAssets() {
  return useQuery({
    queryKey: ["poster-assets"],
    queryFn: async () => (await api.get<PosterAsset[]>("/poster/assets")).data,
    staleTime: 30_000,
  });
}

function kb(bytes: number) {
  return bytes >= 1_048_576
    ? `${(bytes / 1_048_576).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** One thumbnail. The bytes need the bearer token, so they come through the client. */
export function AssetThumb({ id, alt, className }: { id: string; alt: string; className?: string }) {
  const { url, failed } = useAuthedImage(`/poster/assets/${id}/file`);

  if (failed) {
    return (
      <div className={clsx("grid place-items-center bg-slate-100 text-[10px] text-slate-400 dark:bg-slate-800", className)}>
        missing
      </div>
    );
  }
  if (!url) {
    return <div className={clsx("animate-pulse bg-slate-100 dark:bg-slate-800", className)} />;
  }
  return <img src={url} alt={alt} className={className} />;
}

/**
 * Pick a picture for a design, or add one.
 *
 * Uploading and choosing are the same screen on purpose: an agent who opens this
 * wanting to place a photo they have not uploaded yet should not have to find a
 * settings page first, and the picture they just added is the one they want
 * selected — so it is, straight away.
 *
 * The refusal from the server is shown verbatim. "Posters take PNG, JPEG, WebP or
 * GIF images. That file is application/pdf." tells an agent what to do next;
 * "Upload failed" does not.
 */
export function AssetPicker({
  open,
  onClose,
  onPick,
  selectedId,
  title = "Choose an image",
}: {
  open: boolean;
  onClose: () => void;
  onPick: (asset: PosterAsset) => void;
  selectedId?: string | null;
  title?: string;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const { data: assets, isLoading } = usePosterAssets();

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return (await api.post<PosterAsset>("/poster/assets", body)).data;
    },
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: ["poster-assets"] });
      toast(`${asset.name} added`);
      onPick(asset); // what you just uploaded is what you meant to use
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/poster/assets/${id}`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["poster-assets"] });
      toast("Image deleted");
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const take = (files: FileList | null) => {
    const file = files?.[0];
    if (file) upload.mutate(file);
  };

  return (
    <Modal open={open} onClose={onClose} title={title} wide>
      <div className="space-y-4">
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); take(e.dataTransfer.files); }}
          className={clsx(
            "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors",
            dragging
              ? "border-primary-400 bg-primary-50/60 dark:bg-primary-950/30"
              : "border-slate-200 dark:border-slate-700"
          )}
        >
          {upload.isPending ? (
            <span className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 size={15} className="animate-spin" /> Uploading…
            </span>
          ) : (
            <>
              <ImagePlus size={22} className="text-slate-400" />
              <p className="text-sm text-slate-600 dark:text-slate-300">
                Drop a picture here, or
                <button
                  className="btn-ghost !px-1.5 !py-0.5 !text-sm text-primary-600 dark:text-primary-400"
                  onClick={() => fileInput.current?.click()}
                >
                  browse
                </button>
              </p>
              <p className="text-xs text-slate-400">PNG, JPEG, WebP or GIF · up to 8 MB</p>
            </>
          )}
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            onChange={(e) => { take(e.target.files); e.target.value = ""; }}
          />
        </div>

        {isLoading ? (
          <p className="py-6 text-center text-sm text-slate-400">Loading your images…</p>
        ) : (assets ?? []).length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">
            Nothing uploaded yet — the first picture you add lands here.
          </p>
        ) : (
          <div className="grid max-h-[22rem] grid-cols-2 gap-3 overflow-y-auto sm:grid-cols-4">
            {(assets ?? []).map((asset) => (
              <div
                key={asset.id}
                className={clsx(
                  "group relative overflow-hidden rounded-lg border transition-colors",
                  asset.id === selectedId
                    ? "border-primary-500 ring-2 ring-primary-500/30"
                    : "border-slate-200 hover:border-primary-300 dark:border-slate-700"
                )}
              >
                <button
                  className="block w-full text-left"
                  onClick={() => { onPick(asset); onClose(); }}
                  title={`Use ${asset.name}`}
                >
                  {/* A chequerboard, so a transparent PNG reads as transparent
                      rather than as white on a white card. */}
                  <span
                    className="block h-24 w-full bg-slate-50 dark:bg-slate-800"
                    style={{
                      backgroundImage:
                        "linear-gradient(45deg,rgba(148,163,184,.25) 25%,transparent 25%,transparent 75%,rgba(148,163,184,.25) 75%),linear-gradient(45deg,rgba(148,163,184,.25) 25%,transparent 25%,transparent 75%,rgba(148,163,184,.25) 75%)",
                      backgroundSize: "14px 14px",
                      backgroundPosition: "0 0, 7px 7px",
                    }}
                  >
                    <AssetThumb id={asset.id} alt={asset.name} className="h-24 w-full object-contain" />
                  </span>
                  <span className="block px-2 py-1.5">
                    <span className="block truncate text-xs font-medium">{asset.name}</span>
                    <span className="block text-[11px] text-slate-400">
                      {asset.width}×{asset.height} · {kb(asset.size_bytes)}
                    </span>
                  </span>
                </button>

                {asset.id === selectedId && (
                  <span className="absolute left-1.5 top-1.5 grid h-5 w-5 place-items-center rounded-full bg-primary-600 text-white">
                    <Check size={12} />
                  </span>
                )}
                <button
                  className="absolute right-1.5 top-1.5 rounded-md bg-white/90 p-1 text-red-500 opacity-0 shadow transition-opacity group-hover:opacity-100 dark:bg-slate-900/90"
                  title="Delete this image from the library"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(asset.id)}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-between gap-2">
          <button className="btn-secondary" onClick={() => fileInput.current?.click()}>
            <Upload size={14} /> Upload another
          </button>
          <button className="btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </Modal>
  );
}
