import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { StatusBadge } from "@/components/ui";
import { formatDateTime, fullName } from "@/lib/format";
import { useUserOptions } from "@/lib/options";
import { optStr, reqStr } from "@/lib/zh";
import type { Task } from "@/types";

const schema = z.object({
  title: reqStr("Task title is required"),
  description: optStr,
  priority: z.string(),
  status: z.string(),
  due_date: optStr,
  assigned_to_id: optStr,
});

const defaults = { title: "", description: "", priority: "medium", status: "todo", due_date: "", assigned_to_id: "" };

const PRIORITY = ["low", "medium", "high", "urgent"].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }));
const STATUS = [
  { value: "todo", label: "To do" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
  { value: "cancelled", label: "Cancelled" },
];

export default function Tasks() {
  const users = useUserOptions();

  const fields: FieldDef[] = [
    { name: "title", label: "Task", colSpan: 2 },
    { name: "priority", label: "Priority", type: "select", options: PRIORITY },
    { name: "status", label: "Status", type: "select", options: STATUS },
    { name: "due_date", label: "Due", type: "datetime-local" },
    { name: "assigned_to_id", label: "Assigned to", type: "select", options: users },
    { name: "description", label: "Description", type: "textarea", colSpan: 2 },
  ];

  return (
    <CrudPage<Task>
      title="Tasks"
      endpoint="/tasks"
      module="tasks"
      schema={schema}
      defaults={defaults}
      fields={fields}
      toForm={(t) => ({
        ...defaults,
        ...t,
        assigned_to_id: t.assigned_to_id ?? "",
        due_date: t.due_date ? t.due_date.slice(0, 16) : "",
      })}
      searchPlaceholder="Search tasks…"
      columns={[
        { key: "title", header: "Task", sortable: true, render: (t) => <span className="font-medium">{t.title}</span> },
        { key: "priority", header: "Priority", sortable: true, render: (t) => <StatusBadge value={t.priority} /> },
        { key: "status", header: "Status", sortable: true, render: (t) => <StatusBadge value={t.status} /> },
        { key: "due_date", header: "Due", sortable: true, render: (t) => formatDateTime(t.due_date) },
        { key: "assigned_to", header: "Assigned", render: (t) => fullName(t.assigned_to) },
        { key: "created_by", header: "Created by", render: (t) => fullName(t.created_by) },
      ]}
    />
  );
}
