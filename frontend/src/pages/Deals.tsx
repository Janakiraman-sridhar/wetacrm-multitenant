import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { StatusBadge } from "@/components/ui";
import { formatDate, formatDateTime, formatMoney, fullName } from "@/lib/format";
import { useCompanyOptions, useContactOptions, useStageOptions, useUserOptions } from "@/lib/options";
import { numDefault, optStr, reqStr } from "@/lib/zh";
import type { Deal } from "@/types";

const schema = z.object({
  title: reqStr("Deal title is required"),
  value: numDefault(0),
  currency: z.string().default("INR"),
  expected_close_date: optStr,
  stage_id: optStr,
  company_id: optStr,
  contact_id: optStr,
  owner_id: optStr,
  competitors: optStr,
  notes: optStr,
});

const defaults = {
  title: "", value: 0, currency: "INR", expected_close_date: "", stage_id: "",
  company_id: "", contact_id: "", owner_id: "", competitors: "", notes: "",
};

const dealDefaultColumns = [
  { key: "title", header: "Deal", sortable: true, render: (d: Deal) => <span className="font-medium">{d.title}</span> },
  { key: "value", header: "Value", sortable: true, render: (d: Deal) => formatMoney(d.value, d.currency) },
  { key: "stage", header: "Stage", render: (d: Deal) => d.stage?.name ?? "—" },
  { key: "probability", header: "Prob.", render: (d: Deal) => `${d.probability}%` },
  { key: "status", header: "Status", sortable: true, render: (d: Deal) => <StatusBadge value={d.status} /> },
  { key: "company", header: "Company", render: (d: Deal) => d.company?.name ?? "—" },
  { key: "owner", header: "Owner", render: (d: Deal) => fullName(d.owner) },
  {
    key: "expected_close_date",
    header: "Close date",
    sortable: true,
    render: (d: Deal) => formatDate(d.expected_close_date),
  },
];

const dealExtraColumns = [
  {
    key: "contact",
    header: "Contact",
    render: (d: Deal) => (d.contact ? `${d.contact.first_name} ${d.contact.last_name}`.trim() : "—"),
  },
  { key: "currency", header: "Currency" },
  {
    key: "competitors",
    header: "Competitors",
    render: (d: Deal) => (
      <span className="block max-w-52 truncate" title={d.competitors ?? ""}>
        {d.competitors || "—"}
      </span>
    ),
  },
  { key: "closed_at", header: "Closed at", render: (d: Deal) => formatDateTime((d as any).closed_at) },
  { key: "created_at", header: "Created", sortable: true, render: (d: Deal) => formatDate(d.created_at) },
  {
    key: "notes",
    header: "Notes",
    render: (d: Deal) => (
      <span className="block max-w-64 truncate" title={d.notes ?? ""}>
        {d.notes || "—"}
      </span>
    ),
  },
];

export default function Deals() {
  const users = useUserOptions();
  const companies = useCompanyOptions();
  const contacts = useContactOptions();
  const stages = useStageOptions();

  const fields: FieldDef[] = [
    { name: "title", label: "Deal title", colSpan: 2 },
    { name: "value", label: "Value", type: "number", step: "0.01" },
    { name: "currency", label: "Currency" },
    { name: "stage_id", label: "Stage", type: "select", options: stages },
    { name: "expected_close_date", label: "Expected close", type: "date" },
    { name: "company_id", label: "Company", type: "select", options: companies },
    { name: "contact_id", label: "Contact", type: "select", options: contacts },
    { name: "owner_id", label: "Owner", type: "select", options: users },
    { name: "competitors", label: "Competitors" },
    { name: "notes", label: "Notes", type: "textarea", colSpan: 2 },
  ];

  return (
    <CrudPage<Deal>
      title="Deals"
      endpoint="/deals"
      module="deals"
      schema={schema}
      defaults={defaults}
      fields={fields}
      toForm={(d) => ({
        ...defaults,
        ...d,
        value: Number(d.value),
        stage_id: d.stage_id ?? "",
        company_id: d.company_id ?? "",
        contact_id: d.contact_id ?? "",
        owner_id: d.owner_id ?? "",
        expected_close_date: d.expected_close_date ?? "",
      })}
      searchPlaceholder="Search deals…"
      columns={dealDefaultColumns}
      allColumns={[...dealDefaultColumns, ...dealExtraColumns]}
    />
  );
}
