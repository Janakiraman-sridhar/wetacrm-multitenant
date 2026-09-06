import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertCircle, CheckCircle2, Download, FileDown, FileUp, Loader2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { Modal } from "@/components/Modal";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { API_URL, api, errorMessage, tokenStore } from "@/lib/api";

interface ImportResult {
  created: number;
  failed: number;
  total: number;
  errors: { row: number; message: string }[];
}

async function downloadFile(path: string) {
  const res = await fetch(`${API_URL}/api/v1/io/${path}`, {
    headers: { Authorization: `Bearer ${tokenStore.access}` },
  });
  if (!res.ok) throw new Error("download failed");
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] || "export.csv";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function ImportExport({ entity, module, label }: { entity: string; module: string; label: string }) {
  const { hasPerm } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const canRead = hasPerm(`${module}:read`);
  const canWrite = hasPerm(`${module}:write`);
  if (!canRead && !canWrite) return null;

  const doExport = async () => {
    setExporting(true);
    try {
      await downloadFile(`${entity}/export`);
    } catch {
      toast("Export failed", "error");
    } finally {
      setExporting(false);
    }
  };

  const doTemplate = async () => {
    try {
      await downloadFile(`${entity}/template`);
    } catch {
      toast("Could not download the sample file", "error");
    }
  };

  const doImport = async (file: File) => {
    setBusy(true);
    setResult(null);
    setFileName(file.name);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post<ImportResult>(`/io/${entity}/import`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(data);
      if (data.created > 0) {
        toast(`Imported ${data.created} ${label.toLowerCase()}`);
        queryClient.invalidateQueries();
      }
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const openImport = () => {
    setResult(null);
    setFileName(null);
    setOpen(true);
  };

  return (
    <>
      {canRead && (
        <button className="btn-secondary" onClick={doExport} disabled={exporting} title={`Export all ${label.toLowerCase()} to CSV`}>
          {exporting ? <Loader2 size={15} className="animate-spin" /> : <FileDown size={15} />} Export
        </button>
      )}
      {canWrite && (
        <button className="btn-secondary" onClick={openImport} title={`Import ${label.toLowerCase()} from a CSV file`}>
          <FileUp size={15} /> Import
        </button>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={`Import ${label}`}>
        <div className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Upload a CSV file to bulk-create {label.toLowerCase()}. Not sure about the format? Download the sample file —
            it has every column with an example row.
          </p>

          <button
            onClick={doTemplate}
            className="flex w-full items-center gap-3 rounded-xl border border-primary-100 bg-primary-50/60 p-3 text-left transition-colors hover:bg-primary-100/60 dark:border-primary-900/50 dark:bg-primary-900/20 dark:hover:bg-primary-900/40"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-100 text-primary-600 dark:bg-primary-900/50 dark:text-primary-300">
              <Download size={16} />
            </span>
            <span>
              <span className="block text-sm font-medium">Download sample import file</span>
              <span className="block text-xs text-slate-400">CSV with all column names and an example row</span>
            </span>
          </button>

          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) doImport(f);
              e.target.value = "";
            }}
          />

          {!result && (
            <button
              onClick={() => fileRef.current?.click()}
              disabled={busy}
              className="flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 py-8 text-center transition-colors hover:border-primary-400 hover:bg-slate-50 disabled:opacity-60 dark:border-slate-700 dark:hover:bg-slate-800/50"
            >
              {busy ? (
                <>
                  <Loader2 size={22} className="animate-spin text-primary-500" />
                  <span className="text-sm text-slate-500">Importing {fileName}…</span>
                </>
              ) : (
                <>
                  <Upload size={22} className="text-slate-400" />
                  <span className="text-sm font-medium">Choose a CSV file</span>
                  <span className="text-xs text-slate-400">or drag it onto this area</span>
                </>
              )}
            </button>
          )}

          {result && (
            <div className="space-y-3">
              <div className="flex gap-3">
                <div className="flex flex-1 items-center gap-2.5 rounded-xl border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-900 dark:bg-emerald-950/50">
                  <CheckCircle2 size={20} className="text-emerald-600 dark:text-emerald-400" />
                  <div>
                    <p className="text-lg font-bold leading-none text-emerald-700 dark:text-emerald-300">{result.created}</p>
                    <p className="text-xs text-emerald-600 dark:text-emerald-400">imported</p>
                  </div>
                </div>
                <div
                  className={clsx(
                    "flex flex-1 items-center gap-2.5 rounded-xl border p-3",
                    result.failed > 0
                      ? "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/50"
                      : "border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50"
                  )}
                >
                  <AlertCircle size={20} className={result.failed > 0 ? "text-red-500" : "text-slate-400"} />
                  <div>
                    <p className={clsx("text-lg font-bold leading-none", result.failed > 0 ? "text-red-600 dark:text-red-400" : "text-slate-500")}>
                      {result.failed}
                    </p>
                    <p className="text-xs text-slate-400">skipped</p>
                  </div>
                </div>
              </div>

              {result.errors.length > 0 && (
                <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-200 dark:border-slate-800">
                  <table className="w-full text-sm">
                    <thead>
                      <tr>
                        <th className="th w-16">Row</th>
                        <th className="th">Problem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.errors.map((e, i) => (
                        <tr key={i} className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-800/50">
                          <td className="td tabular-nums text-slate-400">{e.row}</td>
                          <td className="td text-red-600 dark:text-red-400">{e.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="flex justify-end gap-2">
                <button className="btn-secondary" onClick={() => setResult(null)}>
                  Import another file
                </button>
                <button className="btn-primary" onClick={() => setOpen(false)}>
                  Done
                </button>
              </div>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}
