import { useEffect, useState } from "react";

import { api } from "@/lib/api";

/**
 * A generated poster, fetched with the caller's credentials.
 *
 * `<img src>` cannot send an Authorization header, and the poster endpoint needs
 * one — it checks the storage key belongs to your tenant before serving. Putting
 * the token in the query string instead would leak it into browser history, the
 * referer header and any proxy log. So the bytes are fetched by the API client and
 * turned into an object URL.
 */
export function PosterImage({
  fileKey,
  alt,
  className,
}: {
  fileKey: string;
  alt: string;
  className?: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    (async () => {
      try {
        const response = await api.get("/poster/file", {
          params: { key: fileKey },
          responseType: "blob",
        });
        if (cancelled) return;
        objectUrl = URL.createObjectURL(response.data as Blob);
        setUrl(objectUrl);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [fileKey]);

  if (failed) {
    return (
      <div className="grid h-32 place-items-center text-xs text-slate-400">
        Could not load
      </div>
    );
  }
  if (!url) {
    return <div className="h-32 animate-pulse bg-slate-100 dark:bg-slate-800" />;
  }
  return <img src={url} alt={alt} className={className} />;
}

/** Download a poster the same way — through the API client, not a bare link. */
export async function downloadPoster(fileKey: string, filename: string): Promise<void> {
  const response = await api.get("/poster/file", { params: { key: fileKey }, responseType: "blob" });
  const url = URL.createObjectURL(response.data as Blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
