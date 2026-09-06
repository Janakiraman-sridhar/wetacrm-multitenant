import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRightCircle } from "lucide-react";
import { useState } from "react";
import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { Modal } from "@/components/Modal";
import { StatusBadge } from "@/components/ui";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { FilterFieldDef } from "@/lib/filters";
import { formatDate, formatDateTime, fullName } from "@/lib/format";
import { useSourceOptions, useUserOptions } from "@/lib/options";
import { numDefault, optEmail, optStr, reqStr } from "@/lib/zh";
import type { Lead } from "@/types";

const schema = z.object({
  title: reqStr("Lead title is required"),
  contact_name: optStr,
  email: optEmail,
  phone: optStr,
  company_name: optStr,
  source_id: optStr,
  status: z.string(),
  score: numDefault(0),
  assigned_to_id: optStr,
  follow_up_at: optStr,
  notes: optStr,
});

const defaults = {
  title: "", contact_name: "", email: "", phone: "", company_name: "",
  source_id: "", status: "new", score: 0, assigned_to_id: "", follow_up_at: "", notes: "",
};

const STATUS_OPTIONS = ["new", "contacted", "qualified", "unqualified", "converted"].map((s) => ({
  value: s,
  label: s.charAt(0).toUpperCase() + s.slice(1),
}));

function ScorePill({ score }: { score: number }) {
  const tone =
    score >= 70
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300"
      : score >= 40
        ? "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300"
        : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
  return <span className={`badge ${tone}`}>{score}</span>;
}

const leadDefaultColumns = [
  { key: "title", header: "Lead", sortable: true, render: (l: Lead) => <span className="font-medium">{l.title}</span> },
  { key: "company_name", header: "Company" },
  { key: "contact_name", header: "Contact" },
  { key: "source", header: "Source", render: (l: Lead) => l.source?.name ?? "—" },
  { key: "status", header: "Status", sortable: true, render: (l: Lead) => <StatusBadge value={l.status} /> },
  { key: "score", header: "Score", sortable: true, render: (l: Lead) => <ScorePill score={l.score} /> },
  { key: "assigned_to", header: "Assigned", render: (l: Lead) => fullName(l.assigned_to) },
  { key: "created_at", header: "Created", sortable: true, render: (l: Lead) => formatDate(l.created_at) },
];

const leadExtraColumns = [
  { key: "email", header: "Email", render: (l: Lead) => l.email || "—" },
  { key: "phone", header: "Phone", render: (l: Lead) => l.phone || "—" },
  { key: "follow_up_at", header: "Follow-up", render: (l: Lead) => formatDateTime(l.follow_up_at) },
  {
    key: "converted_deal_id",
    header: "Converted to deal",
    render: (l: Lead) =>
      l.converted_deal_id ? (
        <span className="badge bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300">Yes</span>
      ) : (
        "—"
      ),
  },
  {
    key: "notes",
    header: "Notes",
    render: (l: Lead) => (
      <span className="block max-w-64 truncate" title={l.notes ?? ""}>
        {l.notes || "—"}
      </span>
    ),
  },
];

export default function Leads() {
  const users = useUserOptions();
  const sources = useSourceOptions();

  const filterFields: FilterFieldDef[] = [
    { key: "status", label: "Status", type: "select", options: STATUS_OPTIONS },
    { key: "source_id", label: "Source", type: "select", options: sources },
    { key: "assigned_to_id", label: "Assigned to", type: "select", options: users },
    { key: "score", label: "Score", type: "number" },
    { key: "follow_up_at", label: "Follow-up date", type: "date" },
    { key: "created_at", label: "Created date", type: "date" },
  ];
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [converting, setConverting] = useState<Lead | null>(null);
  const [dealValue, setDealValue] = useState("");

  const convertMutation = useMutation({
    mutationFn: async (lead: Lead) =>
      (await api.post(`/leads/${lead.id}/convert`, { value: Number(dealValue) || 0 })).data,
    onSuccess: () => {
      toast("Lead converted to deal 🎉");
      setConverting(null);
      setDealValue("");
      queryClient.invalidateQueries({ queryKey: ["/leads"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const fields: FieldDef[] = [
    { name: "title", label: "Lead title", colSpan: 2, placeholder: "e.g. Acme ERP rollout" },
    { name: "contact_name", label: "Contact person" },
    { name: "company_name", label: "Company" },
    { name: "email", label: "Email", type: "email" },
    { name: "phone", label: "Phone" },
    { name: "source_id", label: "Source", type: "select", options: sources },
    { name: "status", label: "Status", type: "select", options: STATUS_OPTIONS },
    { name: "score", label: "Score (0–100)", type: "number" },
    { name: "assigned_to_id", label: "Assigned to", type: "select", options: users },
    { name: "follow_up_at", label: "Follow-up", type: "datetime-local" },
    { name: "notes", label: "Notes", type: "textarea", colSpan: 2 },
  ];

  return (
    <>
      <CrudPage<Lead>
        title="Leads"
        endpoint="/leads"
        module="leads"
        ioEntity="leads"
        filterFields={filterFields}
        schema={schema}
        defaults={defaults}
        fields={fields}
        toForm={(l) => ({
          ...defaults,
          ...l,
          source_id: l.source_id ?? "",
          assigned_to_id: l.assigned_to_id ?? "",
          follow_up_at: l.follow_up_at ? l.follow_up_at.slice(0, 16) : "",
        })}
        searchPlaceholder="Search leads…"
        columns={leadDefaultColumns}
        allColumns={[...leadDefaultColumns, ...leadExtraColumns]}
        rowActions={(lead) =>
          lead.status !== "converted" ? (
            <button
              className="btn-ghost !p-1.5 text-emerald-600"
              title="Convert to deal"
              onClick={() => setConverting(lead)}
            >
              <ArrowRightCircle size={15} />
            </button>
          ) : null
        }
      />

      <Modal open={!!converting} onClose={() => setConverting(null)} title="Convert lead to deal">
        <p className="text-sm text-slate-500">
          Converting <b>{converting?.title}</b> will create a deal in the pipeline
          {converting?.company_name ? `, a company record for “${converting.company_name}”` : ""} and mark this lead
          as converted.
        </p>
        <div className="mt-4">
          <label className="label">Estimated deal value</label>
          <input
            type="number"
            className="input"
            placeholder="0"
            value={dealValue}
            onChange={(e) => setDealValue(e.target.value)}
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setConverting(null)}>
            Cancel
          </button>
          <button
            className="btn-primary"
            disabled={convertMutation.isPending}
            onClick={() => converting && convertMutation.mutate(converting)}
          >
            {convertMutation.isPending ? "Converting…" : "Convert"}
          </button>
        </div>
      </Modal>
    </>
  );
}
