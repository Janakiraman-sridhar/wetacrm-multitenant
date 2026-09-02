import { ArrowRight, ChartColumnBig, Eye, EyeOff, Lock, Mail, SquareKanban, Target } from "lucide-react";
import { useState } from "react";
import { Navigate } from "react-router-dom";

import logoFull from "@/assets/logo.png";
import logoMark from "@/assets/logo-mark.png";
import { useAuth } from "@/context/AuthContext";
import { errorMessage } from "@/lib/api";

const HIGHLIGHTS = [
  { icon: Target, text: "Capture and score every lead, from first touch to closure" },
  { icon: SquareKanban, text: "A visual pipeline your whole team works from" },
  { icon: ChartColumnBig, text: "Executive reports with the data one click away" },
];

export default function Login() {
  const { user, login, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to="/" replace />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="relative hidden w-[46%] flex-col justify-between overflow-hidden bg-gradient-to-br from-primary-800 via-primary-700 to-sky-700 p-12 text-white lg:flex">
        {/* decorative glows */}
        <div className="pointer-events-none absolute -left-24 -top-24 h-96 w-96 rounded-full bg-sky-400/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -right-16 h-[28rem] w-[28rem] rounded-full bg-primary-400/20 blur-3xl" />
        <div className="pointer-events-none absolute right-24 top-1/3 h-40 w-40 rounded-full bg-emerald-400/10 blur-2xl" />

        <div className="relative flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white p-1.5 shadow-lg">
            <img src={logoMark} alt="" className="h-full w-auto object-contain" />
          </span>
          <span className="text-xl font-bold tracking-tight">WeTa CRM</span>
        </div>

        <div className="relative max-w-md">
          <h1 className="text-4xl font-bold leading-tight">
            Every customer.
            <br />
            One workspace.
          </h1>
          <p className="mt-4 text-primary-100">
            Leads, deals, quotations and support — managed end to end, with the numbers your leadership needs built in.
          </p>
          <ul className="mt-8 space-y-4">
            {HIGHLIGHTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3.5">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
                  <Icon size={17} strokeWidth={1.8} />
                </span>
                <span className="text-sm text-primary-50">{text}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-primary-200/80">
          © {new Date().getFullYear()} WeTa CRM · Enterprise CRM platform
        </p>
      </div>

      {/* Form panel */}
      <div className="flex flex-1 items-center justify-center bg-slate-50 p-6 dark:bg-slate-950">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex flex-col items-center gap-4 lg:hidden">
            <span className="rounded-2xl bg-white p-3 shadow-sm ring-1 ring-slate-200 dark:ring-slate-700">
              <img src={logoFull} alt="WeTa CRM" className="h-20 w-auto object-contain" />
            </span>
          </div>

          <h2 className="text-2xl font-bold">Welcome back</h2>
          <p className="mt-1 text-sm text-slate-400">Sign in to your workspace to continue.</p>

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
            <div>
              <label className="label" htmlFor="password">
                Password
              </label>
              <div className="relative">
                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  required
                  autoComplete="current-password"
                  className="input !py-2.5 !pl-10 !pr-10"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  tabIndex={-1}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                  onClick={() => setShowPassword(!showPassword)}
                  title={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                {error}
              </p>
            )}

            <button type="submit" className="btn-primary w-full !py-2.5" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
              {!busy && <ArrowRight size={16} />}
            </button>
          </form>

          <p className="mt-8 text-center text-xs text-slate-400">
            Forgot your password? Ask an administrator to send you a reset link.
          </p>
        </div>
      </div>
    </div>
  );
}
