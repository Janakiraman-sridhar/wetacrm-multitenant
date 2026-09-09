import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Clock, Download, FileText, Paperclip, Pin, PinOff, Plus, StickyNote, Trash2, Upload, X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Avatar } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { API_URL, api, errorMessage } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";

interface Note {
  id: string;
  body: string;
  is_pinned: boolean;
  created_at: string;
  author?: { id: string; full_name?: string; first_name?: string; last_name?: string } | null;
}

interface Doc {
  id: string;
  name: string;
  mime_type?: string | null;
  size_bytes: number;
  created_at: string;
  uploaded_by?: { first_name?: string; last_name?: string } | null;
}

interface ActivityRow {
  id: string;
  type: string;
  title: string;
  body?: string | null;
  created_at: string;
  user?: { first_name?: string; last_name?: string } | null;
}

const size = (bytes: number) =>
  bytes >= 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

const name = (p?: { first_name?: string; last_name?: string; full_name?: string } | null) =>
  p?.full_name || [p?.first_name, p?.last_name].filter(Boolean).join(" ") || "Someone";

/**
 * Everything about one record that is not a form field.
 *
 * Notes, files and the timeline have been written to the database since these
 * modules were built and none of them had a screen — a customer accumulated dated
 * notes nobody could read, and a policy could not carry the PDF it was issued as.
 * The edit modal was the wrong home for them: they are read far more often than
 * they are changed, and you should not have to enter edit mode to look.
 *
 * A drawer rather than a page because it opens over the list an agent is working
 * through, and closing it puts them back exactly where they were.
 */
export function RecordPanel({
  open,
  onClose,
  entityType,
  entityId,
  title,
  subtitle,
}: {
  open: boolean;
  onClose: () => void;
  /** `contact`, `policy`, `loan` … — what `documents` and `activities` index by. */
  entityType: string;
  entityId: string;
  title: string;
  subtitle?: string;
}) {
  const { hasPerm } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<"notes" | "files" | "activity">("notes");
  const [draft, setDraft] = useState("");
  const [dragging, setDragging] = useState(false);

  // Only customers have the dated-note table; everything else starts on files.
  const hasNotes = entityType === "contact";
  useEffect(() => {
    if (open) setTab(hasNotes ? "notes" : "files");
  }, [open, hasNotes, entityId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const notes = useQuery({
    queryKey: ["record-notes", entityId],
    queryFn: async () => (await api.get<Note[]>(`/contacts/${entityId}/notes`)).data,
    enabled: open && hasNotes,
  });

  const docs = useQuery({
    queryKey: ["record-docs", entityType, entityId],
    queryFn: async () =>
      (await api.get<{ items: Doc[] }>("/documents", {
        params: { entity_type: entityType, entity_id: entityId, page_size: 100 },
      })).data.items,
    enabled: open,
  });

  const activity = useQuery({
    queryKey: ["record-activity", entityType, entityId],
    queryFn: async () =>
      (await api.get<{ items: ActivityRow[] }>("/activities", {
        params: { entity_type: entityType, entity_id: entityId, page_size: 50 },
      })).data.items,
    enabled: open,
  });

  const refreshNotes = () => {
    queryClient.invalidateQueries({ queryKey: ["record-notes", entityId] });
    queryClient.invalidateQueries({ queryKey: ["record-activity", entityType, entityId] });
  };

  const addNote = useMutation({
    mutationFn: async (body: string) =>
      (await api.post(`/contacts/${entityId}/notes`, { body, is_pinned: false })).data,
    onSuccess: () => { setDraft(""); refreshNotes(); },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const pinNote = useMutation({
    mutationFn: async (note: Note) =>
      (await api.patch(`/contacts/${entityId}/notes/${note.id}`,
                       { body: note.body, is_pinned: !note.is_pinned })).data,
    onSuccess: refreshNotes,
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const removeNote = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/contacts/${entityId}/notes/${id}`)).data,
    onSuccess: refreshNotes,
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return (await api.post("/documents", body, {
        params: { entity_type: entityType, entity_id: entityId },
      })).data;
    },
    onSuccess: (doc: Doc) => {
      toast(`${doc.name} attached`);
      queryClient.invalidateQueries({ queryKey: ["record-docs", entityType, entityId] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const removeDoc = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/documents/${id}`)).data,
    onSuccess: () => {
      toast("File removed");
      queryClient.invalidateQueries({ queryKey: ["record-docs", entityType, entityId] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  /** Fetch a short-lived signed URL and let the browser take it from there. */
  const openDoc = async (doc: Doc, inline: boolean) => {
    try {
      const { data } = await api.get<{ url: string }>(`/documents/${doc.id}/link`, {
        params: { inline },
      });
      window.open(`${API_URL}${data.url}`, "_blank", "noopener");
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  };

  const take = (files: FileList | null) => {
    const file = files?.[0];
    if (file) upload.mutate(file);
  };

  if (!open) return null;

  const canWriteNotes = hasPerm("contacts:write");
  const canWriteDocs = hasPerm("documents:write");
  const TABS = [
    ...(hasNotes ? [{ id: "notes" as const, label: "Notes", icon: StickyNote, count: notes.data?.length }] : []),
    { id: "files" as const, label: "Files", icon: Paperclip, count: docs.data?.length },
    { id: "activity" as const, label: "History", icon: Clock, count: activity.data?.length },
  ];

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-[2px]" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-lg flex-col border-l border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        <header className="flex items-start gap-3 border-b border-slate-100 p-4 dark:border-slate-800">
          <div className="min-w-0 flex-1">
            <h2 className="truncate font-semibold">{title}</h2>
            {subtitle && <p className="truncate text-xs text-slate-400">{subtitle}</p>}
          </div>
          <button className="btn-ghost !p-1.5 text-slate-400" onClick={onClose} title="Close">
            <X size={18} />
          </button>
        </header>

        <nav className="flex gap-1 border-b border-slate-100 px-3 dark:border-slate-800">
          {TABS.map(({ id, label, icon: Icon, count }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={clsx(
                "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors",
                tab === id
                  ? "border-primary-600 text-primary-700 dark:border-primary-400 dark:text-primary-300"
                  : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              )}
            >
              <Icon size={14} /> {label}
              {!!count && <span className="text-xs text-slate-400">{count}</span>}
            </button>
          ))}
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {tab === "notes" && (
            <div className="space-y-3">
              {canWriteNotes && (
                <div>
                  <textarea
                    className="input"
                    rows={2}
                    placeholder="What happened? Spoke to them, promised a quote…"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                  />
                  <div className="mt-1.5 flex justify-end">
                    <button
                      className="btn-primary !py-1.5 text-xs"
                      disabled={!draft.trim() || addNote.isPending}
                      onClick={() => addNote.mutate(draft.trim())}
                    >
                      <Plus size={13} /> Add note
                    </button>
                  </div>
                </div>
              )}

              {(notes.data ?? []).map((note) => (
                <article
                  key={note.id}
                  className={clsx(
                    "rounded-lg border p-3",
                    note.is_pinned
                      ? "border-amber-200 bg-amber-50/60 dark:border-amber-900/60 dark:bg-amber-950/20"
                      : "border-slate-200 dark:border-slate-700"
                  )}
                >
                  <p className="whitespace-pre-wrap text-sm">{note.body}</p>
                  <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
                    <Avatar first={note.author?.first_name ?? "?"} last={note.author?.last_name ?? ""} size={18} />
                    <span className="min-w-0 flex-1 truncate">
                      {name(note.author)} · {timeAgo(note.created_at)}
                    </span>
                    {canWriteNotes && (
                      <>
                        <button
                          className="btn-ghost !p-1"
                          title={note.is_pinned ? "Unpin" : "Pin to the top"}
                          onClick={() => pinNote.mutate(note)}
                        >
                          {note.is_pinned ? <PinOff size={12} /> : <Pin size={12} />}
                        </button>
                        <button
                          className="btn-ghost !p-1 hover:text-red-500"
                          title="Delete this note"
                          onClick={() => removeNote.mutate(note.id)}
                        >
                          <Trash2 size={12} />
                        </button>
                      </>
                    )}
                  </div>
                </article>
              ))}
              {notes.isSuccess && (notes.data ?? []).length === 0 && (
                <p className="py-8 text-center text-sm text-slate-400">
                  No notes yet. What you write here is dated and attributed, unlike the
                  single notes box on the record.
                </p>
              )}
            </div>
          )}

          {tab === "files" && (
            <div className="space-y-3">
              {canWriteDocs && (
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => { e.preventDefault(); setDragging(false); take(e.dataTransfer.files); }}
                  className={clsx(
                    "flex flex-col items-center gap-1.5 rounded-xl border-2 border-dashed px-4 py-5 text-center transition-colors",
                    dragging
                      ? "border-primary-400 bg-primary-50/60 dark:bg-primary-950/30"
                      : "border-slate-200 dark:border-slate-700"
                  )}
                >
                  <Upload size={18} className="text-slate-400" />
                  <p className="text-sm text-slate-600 dark:text-slate-300">
                    Drop a file here, or
                    <button
                      className="btn-ghost !px-1.5 !py-0.5 !text-sm text-primary-600 dark:text-primary-400"
                      onClick={() => fileInput.current?.click()}
                    >
                      browse
                    </button>
                  </p>
                  <p className="text-xs text-slate-400">
                    {upload.isPending ? "Uploading…" : "Policy copy, RC, KYC — up to 25 MB"}
                  </p>
                  <input
                    ref={fileInput}
                    type="file"
                    className="hidden"
                    onChange={(e) => { take(e.target.files); e.target.value = ""; }}
                  />
                </div>
              )}

              <ul className="space-y-1.5">
                {(docs.data ?? []).map((doc) => (
                  <li
                    key={doc.id}
                    className="flex items-center gap-2 rounded-lg border border-slate-200 p-2.5 dark:border-slate-700"
                  >
                    <FileText size={16} className="shrink-0 text-slate-400" />
                    <button
                      className="min-w-0 flex-1 text-left"
                      title="Open in a new tab"
                      onClick={() => openDoc(doc, true)}
                    >
                      <span className="block truncate text-sm font-medium">{doc.name}</span>
                      <span className="block text-xs text-slate-400">
                        {size(doc.size_bytes)} · {name(doc.uploaded_by)} · {timeAgo(doc.created_at)}
                      </span>
                    </button>
                    <button
                      className="btn-ghost !p-1.5 shrink-0 text-slate-400"
                      title="Download"
                      onClick={() => openDoc(doc, false)}
                    >
                      <Download size={14} />
                    </button>
                    {hasPerm("documents:delete") && (
                      <button
                        className="btn-ghost !p-1.5 shrink-0 text-slate-400 hover:text-red-500"
                        title="Remove this file"
                        onClick={() => removeDoc.mutate(doc.id)}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </li>
                ))}
                {docs.isSuccess && (docs.data ?? []).length === 0 && (
                  <li className="py-8 text-center text-sm text-slate-400">
                    Nothing attached to this record yet.
                  </li>
                )}
              </ul>
            </div>
          )}

          {tab === "activity" && (
            <ol className="space-y-3">
              {(activity.data ?? []).map((row) => (
                <li key={row.id} className="flex gap-3">
                  <span className="relative flex flex-col items-center">
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary-500" />
                    <span className="mt-1 w-px flex-1 bg-slate-200 dark:bg-slate-700" />
                  </span>
                  <div className="min-w-0 flex-1 pb-1">
                    <p className="text-sm">{row.title}</p>
                    {row.body && (
                      <p className="mt-0.5 whitespace-pre-wrap text-xs text-slate-500 dark:text-slate-400">
                        {row.body}
                      </p>
                    )}
                    <p className="mt-0.5 text-xs text-slate-400">
                      {row.user ? `${name(row.user)} · ` : ""}
                      {formatDateTime(row.created_at)}
                    </p>
                  </div>
                </li>
              ))}
              {activity.isSuccess && (activity.data ?? []).length === 0 && (
                <li className="py-8 text-center text-sm text-slate-400">
                  Nothing recorded for this one yet.
                </li>
              )}
            </ol>
          )}
        </div>
      </aside>
    </div>
  );
}
