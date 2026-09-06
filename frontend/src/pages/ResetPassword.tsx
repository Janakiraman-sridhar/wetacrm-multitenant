import { ArrowLeft, CheckCircle2, Eye, EyeOff, Lock } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import logoFull from "@/assets/logo.png";
import logoFullDark from "@/assets/logo-dark.png";
import { api, errorMessage } from "@/lib/api";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    if (password !== confirm) return setError("The two passwords don't match.");
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/reset-password", { token, new_password: password });
      setDone(true);
      setTimeout(() => navigate("/login"), 2500);
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

        {!token ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-lg font-semibold">This link is invalid</h2>
            <p className="mt-1.5 text-sm text-slate-500">
              The reset link is missing or malformed. Please request a new one.
            </p>
            <Link to="/forgot-password" className="btn-primary mt-5 w-full justify-center">
              Request a new link
            </Link>
          </div>
        ) : done ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-400">
              <CheckCircle2 size={24} />
            </span>
            <h2 className="text-lg font-semibold">Password updated</h2>
            <p className="mt-1.5 text-sm text-slate-500">You can now sign in with your new password. Redirecting…</p>
            <Link to="/login" className="btn-secondary mt-5 w-full justify-center">
              Go to sign in
            </Link>
          </div>
        ) : (
          <>
            <h2 className="text-2xl font-bold">Set a new password</h2>
            <p className="mt-1 text-sm text-slate-400">Choose a strong password you don't use anywhere else.</p>

            <form onSubmit={submit} className="mt-8 space-y-5">
              <div>
                <label className="label" htmlFor="password">
                  New password
                </label>
                <div className="relative">
                  <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    id="password"
                    type={show ? "text" : "password"}
                    required
                    autoFocus
                    autoComplete="new-password"
                    className="input !py-2.5 !pl-10 !pr-10"
                    placeholder="At least 8 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    tabIndex={-1}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                    onClick={() => setShow(!show)}
                    title={show ? "Hide password" : "Show password"}
                  >
                    {show ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
              <div>
                <label className="label" htmlFor="confirm">
                  Confirm password
                </label>
                <div className="relative">
                  <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    id="confirm"
                    type={show ? "text" : "password"}
                    required
                    autoComplete="new-password"
                    className="input !py-2.5 !pl-10"
                    placeholder="Re-enter your new password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                  />
                </div>
              </div>

              {error && (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                  {error}
                </p>
              )}

              <button type="submit" className="btn-primary w-full !py-2.5" disabled={busy}>
                {busy ? "Updating…" : "Update password"}
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
