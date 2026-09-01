import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { StatusBadge } from "@/components/ui";
import { formatDate, formatMoney, fullName } from "@/lib/format";
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
      columns={[
        { key: "title", header: "Deal", sortable: true, render: (d) => <span className="font-medium">{d.title}</span> },
        { key: "value", header: "Value", sortable: true, render: (d) => formatMoney(d.value, d.currency) },
        { key: "stage", header: "Stage", render: (d) => d.stage?.name ?? "—" },
        { key: "probability", header: "Prob.", render: (d) => `${d.probability}%` },
        { key: "status", header: "Status", sortable: true, render: (d) => <StatusBadge value={d.status} /> },
        { key: "company", header: "Company", render: (d) => d.company?.name ?? "—" },
        { key: "owner", header: "Owner", render: (d) => fullName(d.owner) },
        {
          key: "expected_close_date",
          header: "Close date",
          sortable: true,
          render: (d) => formatDate(d.expected_close_date),
        },
      ]}
    />
  );
}
