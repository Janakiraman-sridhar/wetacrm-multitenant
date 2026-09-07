import { useMutation } from "@tanstack/react-query";
import { Eye, EyeOff, Loader2, ShieldAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";

const REVEAL_SECONDS = 30;

/**
 * A masked identity number with an audited reveal.
 *
 * The full value is never in the record the page already holds — it is fetched on
 * demand from an endpoint that requires its own permission and writes an audit row.
 * It is then shown for 30 seconds and re-masked, so it does not sit on a screen
 * someone walks away from.
 */
export function MaskedField({
  contactId,
  field,
  label,
  masked,
  present,
  unavailableReason,
}: {
  contactId: string;
  field: "pan" | "aadhaar";
  label: string;
  masked: string | null;
  present: boolean;
  /** Shown instead of the reveal control when the full value is not stored. */
  unavailableReason?: string | null;
}) {
  const { toast } = useToast();
  const [revealed, setRevealed] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, []);

  const reveal = useMutation({
    mutationFn: async () =>
      (await api.post(`/contacts/${contactId}/reveal`, { field })).data as { value: string },
    onSuccess: ({ value }) => {
      setRevealed(value);
      setCountdown(REVEAL_SECONDS);
      if (timer.current) window.clearInterval(timer.current);
      timer.current = window.setInterval(() => {
        setCountdown((seconds) => {
          if (seconds <= 1) {
            setRevealed(null);
            if (timer.current) window.clearInterval(timer.current);
            return 0;
          }
          return seconds - 1;
        });
      }, 1000);
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const hide = () => {
    setRevealed(null);
    setCountdown(0);
    if (timer.current) window.clearInterval(timer.current);
  };

  if (!present) {
    return (
      <div>
        <label className="label">{label}</label>
        <p className="text-sm text-slate-400">Not on file</p>
      </div>
    );
  }

  return (
    <div>
      <label className="label">{label}</label>
      <div className="flex items-center gap-2">
        <code
          className={clsxish(revealed)}
          title={revealed ? "Re-masks automatically" : "Masked"}
        >
          {revealed ?? masked ?? "••••"}
        </code>

        {unavailableReason ? (
          <span
            className="flex items-center gap-1 text-xs text-slate-400"
            title={unavailableReason}
          >
            <ShieldAlert size={13} /> partial
          </span>
        ) : revealed ? (
          <button type="button" className="btn-ghost !p-1.5" onClick={hide} title="Hide now">
            <EyeOff size={15} />
            <span className="text-xs tabular-nums">{countdown}s</span>
          </button>
        ) : (
          <button
            type="button"
            className="btn-ghost !p-1.5"
            onClick={() => reveal.mutate()}
            disabled={reveal.isPending}
            title="Show the full number. This view is recorded."
          >
            {reveal.isPending ? <Loader2 size={15} className="animate-spin" /> : <Eye size={15} />}
          </button>
        )}
      </div>
      {!unavailableReason && (
        <p className="mt-1 text-xs text-slate-400">
          Stored encrypted. Viewing the full number is recorded against your account.
        </p>
      )}
      {unavailableReason && <p className="mt-1 text-xs text-slate-400">{unavailableReason}</p>}
    </div>
  );
}

function clsxish(revealed: string | null): string {
  return [
    "rounded-lg border px-2.5 py-1.5 font-mono text-sm tracking-wider",
    revealed
      ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200"
      : "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200",
  ].join(" ");
}
