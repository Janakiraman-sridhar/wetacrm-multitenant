import { ArrowLeft, ArrowRight, CheckCircle2, Mail } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import logoFull from "@/assets/logo.png";
import logoFullDark from "@/assets/logo-dark.png";
import { api, errorMessage } from "@/lib/api";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 dark:bg-slate-950">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <img src={logoFull} alt="WeTa CRM" className="h-16 w-auto object-contain dark:hidden" />
          <img src={logoFullDark} alt="WeTa CRM" className="hidden h-16 w-auto object-contain dark:block" />
        </div>

        {sent ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-400">
              <CheckCircle2 size={24} />
            </span>
            <h2 className="text-lg font-semibold">Check your inbox</h2>
            <p className="mt-1.5 text-sm text-slate-500">
              If an account exists for <b>{email}</b>, we've sent a link to reset your password. It expires in 30 minutes.
            </p>
            <Link to="/login" className="btn-secondary mt-5 w-full justify-center">
              <ArrowLeft size={15} /> Back to sign in
            </Link>
          </div>
        ) : (
          <>
            <h2 className="text-2xl font-bold">Reset your password</h2>
            <p className="mt-1 text-sm text-slate-400">
              Enter your account email and we'll send you a link to set a new password.
            </p>

            <form onSubmit={submit} className="mt-8 space-y-5">
              <div>
                <label className="label" htmlFor="email">
                  Email
                </label>
                <div className="relative">
                  <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    id="email"
                    type="email"
                    required
                    autoFocus
                    autoComplete="email"
                    className="input !py-2.5 !pl-10"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
              </div>

              {error && (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                  {error}
                </p>
              )}

              <button type="submit" className="btn-primary w-full !py-2.5" disabled={busy || !email}>
                {busy ? "Sending…" : "Send reset link"}
                {!busy && <ArrowRight size={16} />}
              </button>
            </form>

            <p className="mt-8 text-center text-sm">
              <Link to="/login" className="inline-flex items-center gap-1 text-slate-400 hover:text-primary-600 dark:hover:text-primary-400">
                <ArrowLeft size={14} /> Back to sign in
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
