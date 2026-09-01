import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "@/lib/api";

const TYPE_ROUTES: Record<string, string> = {
  company: "/companies",
  contact: "/contacts",
  lead: "/leads",
  deal: "/deals",
  task: "/tasks",
  project: "/projects",
};

interface Hit {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  extra: string;
}

export function GlobalSearch() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const { data } = useQuery({
    queryKey: ["global-search", q],
    queryFn: async () => (await api.get("/search", { params: { q } })).data,
    enabled: q.trim().length >= 2,
    staleTime: 10_000,
  });

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const groups: [string, Hit[]][] = data
    ? Object.entries(data.results as Record<string, Hit[]>).filter(([, hits]) => hits.length > 0)
    : [];

  return (
    <div ref={boxRef} className="relative hidden w-full max-w-md md:block">
      <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
      <input
        className="input !pl-9"
        placeholder="Search leads, companies, deals…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
      />
      {open && q.trim().length >= 2 && (
        <div className="card absolute left-0 right-0 top-11 z-40 max-h-96 overflow-y-auto p-2 shadow-xl">
          {groups.length === 0 && <p className="px-3 py-4 text-sm text-slate-400">No results for “{q}”.</p>}
          {groups.map(([group, hits]) => (
            <div key={group} className="mb-1">
              <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{group}</p>
              {hits.map((hit) => (
                <button
                  key={hit.id}
                  className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
                  onClick={() => {
                    setOpen(false);
                    setQ("");
                    navigate(`${TYPE_ROUTES[hit.type] ?? "/"}?id=${hit.id}`);
                  }}
                >
                  <span className="font-medium">{hit.title}</span>
                  {hit.subtitle && <span className="ml-2 text-xs text-slate-400">{hit.subtitle}</span>}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
