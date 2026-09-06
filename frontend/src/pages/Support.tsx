import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { StatusBadge } from "@/components/ui";
import { formatDate, fullName } from "@/lib/format";
import { useCompanyOptions, useContactOptions, useUserOptions } from "@/lib/options";
import { optStr, reqStr } from "@/lib/zh";
import type { Ticket } from "@/types";

const schema = z.object({
  subject: reqStr("Subject is required"),
  description: optStr,
  company_id: optStr,
  contact_id: optStr,
  priority: z.string(),
  status: z.string(),
  assigned_to_id: optStr,
  resolution: optStr,
});

const defaults = {
  subject: "", description: "", company_id: "", contact_id: "",
  priority: "medium", status: "open", assigned_to_id: "", resolution: "",
};

const PRIORITY = ["low", "medium", "high", "urgent"].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }));
const STATUS = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

const ticketDefaultColumns = [
  { key: "number", header: "#", sortable: true, render: (t: Ticket) => <span className="font-mono text-xs">{t.number}</span> },
  { key: "subject", header: "Subject", sortable: true, render: (t: Ticket) => <span className="font-medium">{t.subject}</span> },
  { key: "company", header: "Company", render: (t: Ticket) => t.company?.name ?? "—" },
  { key: "priority", header: "Priority", sortable: true, render: (t: Ticket) => <StatusBadge value={t.priority} /> },
  { key: "status", header: "Status", sortable: true, render: (t: Ticket) => <StatusBadge value={t.status} /> },
  { key: "assigned_to", header: "Assigned", render: (t: Ticket) => fullName(t.assigned_to) },
  { key: "created_at", header: "Created", sortable: true, render: (t: Ticket) => formatDate(t.created_at) },
];

const ticketExtraColumns = [
  {
    key: "description",
    header: "Description",
    render: (t: Ticket) => (
      <span className="block max-w-64 truncate" title={t.description ?? ""}>
        {t.description || "—"}
      </span>
    ),
  },
  {
    key: "resolution",
    header: "Resolution",
    render: (t: Ticket) => (
      <span className="block max-w-64 truncate" title={t.resolution ?? ""}>
        {t.resolution || "—"}
      </span>
    ),
  },
];

export default function Support() {
  const users = useUserOptions();
  const companies = useCompanyOptions();
  const contacts = useContactOptions();

  const fields: FieldDef[] = [
    { name: "subject", label: "Subject", colSpan: 2 },
    { name: "company_id", label: "Company", type: "select", options: companies },
    { name: "contact_id", label: "Contact", type: "select", options: contacts },
    { name: "priority", label: "Priority", type: "select", options: PRIORITY },
    { name: "status", label: "Status", type: "select", options: STATUS },
    { name: "assigned_to_id", label: "Assigned to", type: "select", options: users },
    { name: "description", label: "Description", type: "textarea", colSpan: 2 },
    { name: "resolution", label: "Resolution", type: "textarea", colSpan: 2 },
  ];

  return (
    <CrudPage<Ticket>
      title="Support Tickets"
      singular="Ticket"
      endpoint="/tickets"
      module="support"
      ioEntity="support"
      schema={schema}
      defaults={defaults}
      fields={fields}
      toForm={(t) => ({
        ...defaults,
        ...t,
        company_id: t.company_id ?? "",
        contact_id: t.contact_id ?? "",
        assigned_to_id: t.assigned_to_id ?? "",
      })}
      searchPlaceholder="Search tickets…"
      columns={ticketDefaultColumns}
      allColumns={[...ticketDefaultColumns, ...ticketExtraColumns]}
    />
  );
}
