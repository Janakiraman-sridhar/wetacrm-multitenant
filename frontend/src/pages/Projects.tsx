import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { StatusBadge } from "@/components/ui";
import { formatDate, formatMoney, fullName } from "@/lib/format";
import { useCompanyOptions, useUserOptions } from "@/lib/options";
import { optNum, optStr, reqStr } from "@/lib/zh";
import type { Project } from "@/types";

const schema = z.object({
  name: reqStr("Project name is required"),
  description: optStr,
  company_id: optStr,
  status: z.string(),
  start_date: optStr,
  end_date: optStr,
  budget: optNum,
  owner_id: optStr,
});

const defaults = {
  name: "", description: "", company_id: "", status: "planned",
  start_date: "", end_date: "", budget: "", owner_id: "",
};

const STATUS = [
  { value: "planned", label: "Planned" },
  { value: "active", label: "Active" },
  { value: "on_hold", label: "On hold" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

export default function Projects() {
  const users = useUserOptions();
  const companies = useCompanyOptions();

  const fields: FieldDef[] = [
    { name: "name", label: "Project name", colSpan: 2 },
    { name: "company_id", label: "Customer", type: "select", options: companies },
    { name: "status", label: "Status", type: "select", options: STATUS },
    { name: "start_date", label: "Start date", type: "date" },
    { name: "end_date", label: "End date", type: "date" },
    { name: "budget", label: "Budget", type: "number", step: "0.01" },
    { name: "owner_id", label: "Project owner", type: "select", options: users },
    { name: "description", label: "Description", type: "textarea", colSpan: 2 },
  ];

  return (
    <CrudPage<Project>
      title="Projects"
      endpoint="/projects"
      module="projects"
      schema={schema}
      defaults={defaults}
      fields={fields}
      toForm={(p) => ({
        ...defaults,
        ...p,
        company_id: p.company_id ?? "",
        owner_id: p.owner?.id ?? "",
        budget: p.budget ?? "",
        start_date: p.start_date ?? "",
        end_date: p.end_date ?? "",
      })}
      searchPlaceholder="Search projects…"
      columns={[
        { key: "name", header: "Project", sortable: true, render: (p) => <span className="font-medium">{p.name}</span> },
        { key: "company", header: "Customer", render: (p) => p.company?.name ?? "—" },
        { key: "status", header: "Status", sortable: true, render: (p) => <StatusBadge value={p.status} /> },
        {
          key: "tasks",
          header: "Progress",
          render: (p) => {
            const done = p.tasks.filter((t) => t.status === "done").length;
            return p.tasks.length ? `${done}/${p.tasks.length} tasks` : "—";
          },
        },
        { key: "budget", header: "Budget", render: (p) => (p.budget != null ? formatMoney(p.budget) : "—") },
        { key: "owner", header: "Owner", render: (p) => fullName(p.owner) },
        { key: "end_date", header: "Due", sortable: true, render: (p) => formatDate(p.end_date) },
      ]}
    />
  );
}
