import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { StatusBadge } from "@/components/ui";
import { FilterFieldDef } from "@/lib/filters";
import { formatDate, formatDateTime, formatMoney, fullName } from "@/lib/format";
import { useCompanyOptions, useContactOptions, useStageOptions, useTagOptions, useUserOptions } from "@/lib/options";
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
  tags: z.array(z.string()).default([]),
});

const defaults = {
  title: "", value: 0, currency: "INR", expected_close_date: "", stage_id: "",
  company_id: "", contact_id: "", owner_id: "", competitors: "", notes: "", tags: [] as string[],
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
    key: "tags",
    header: "Tags",
    render: (d: Deal) =>
      d.tags?.length ? (
        <span className="flex max-w-52 flex-wrap gap-1">
          {d.tags.map((t) => (
            <span key={t} className="badge bg-primary-50 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">
              {t}
            </span>
          ))}
        </span>
      ) : (
        "—"
      ),
  },
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
  const tags = useTagOptions();

  const filterFields: FilterFieldDef[] = [
    {
      key: "status", label: "Status", type: "select",
      options: [{ value: "open", label: "Open" }, { value: "won", label: "Won" }, { value: "lost", label: "Lost" }],
    },
    { key: "stage_id", label: "Stage", type: "select", options: stages },
    { key: "owner_id", label: "Owner", type: "select", options: users },
    { key: "company_id", label: "Company", type: "select", options: companies },
    { key: "value", label: "Value", type: "number" },
    { key: "expected_close_date", label: "Expected close", type: "date" },
    { key: "created_at", label: "Created date", type: "date" },
  ];

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
    { name: "tags", label: "Products / services (tags)", type: "multiselect", options: tags, colSpan: 2, placeholder: "Tag products or services…" },
    { name: "notes", label: "Notes", type: "textarea", colSpan: 2 },
  ];

  return (
    <CrudPage<Deal>
      title="Deals"
      endpoint="/deals"
      module="deals"
      ioEntity="deals"
      filterFields={filterFields}
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
        tags: d.tags ?? [],
      })}
      searchPlaceholder="Search deals…"
      columns={dealDefaultColumns}
      allColumns={[...dealDefaultColumns, ...dealExtraColumns]}
    />
  );
}
