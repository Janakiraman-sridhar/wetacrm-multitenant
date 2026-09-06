import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { Avatar } from "@/components/ui";
import { FilterFieldDef } from "@/lib/filters";
import { formatDate, fullName } from "@/lib/format";
import { useUserOptions } from "@/lib/options";
import { optEmail, optStr, reqStr } from "@/lib/zh";
import type { Company } from "@/types";

const schema = z.object({
  name: reqStr("Company name is required"),
  industry: optStr,
  website: optStr,
  gst_number: optStr,
  phone: optStr,
  email: optEmail,
  address: optStr,
  city: optStr,
  state: optStr,
  country: optStr,
  postal_code: optStr,
  notes: optStr,
  owner_id: optStr,
});

const defaults = {
  name: "", industry: "", website: "", gst_number: "", phone: "", email: "",
  address: "", city: "", state: "", country: "", postal_code: "", notes: "", owner_id: "",
};

export default function Companies() {
  const users = useUserOptions();

  const filterFields: FilterFieldDef[] = [
    { key: "industry", label: "Industry", type: "text" },
    { key: "city", label: "City", type: "text" },
    { key: "country", label: "Country", type: "text" },
    { key: "owner_id", label: "Account Manager", type: "select", options: users },
    { key: "created_at", label: "Created date", type: "date" },
  ];

  const fields: FieldDef[] = [
    { name: "name", label: "Company name", colSpan: 2, section: "Company details", placeholder: "e.g. Acme Industries" },
    { name: "industry", label: "Industry", section: "Company details", placeholder: "e.g. Manufacturing" },
    { name: "website", label: "Website", section: "Company details", placeholder: "https://acme.com" },
    { name: "gst_number", label: "GST number", section: "Company details", placeholder: "22AAAAA0000A1Z5" },
    { name: "owner_id", label: "Account manager", type: "select", options: users, section: "Company details", placeholder: "Assign a manager…" },
    { name: "email", label: "Email", type: "email", section: "Contact information", placeholder: "hello@acme.com" },
    { name: "phone", label: "Phone", section: "Contact information", placeholder: "+91 98765 43210" },
    { name: "address", label: "Street address", type: "textarea", colSpan: 2, section: "Address" },
    { name: "city", label: "City", section: "Address" },
    { name: "state", label: "State", section: "Address" },
    { name: "country", label: "Country", section: "Address" },
    { name: "postal_code", label: "Postal code", section: "Address" },
    { name: "notes", label: "Notes", type: "textarea", colSpan: 2, section: "Additional", placeholder: "Anything the team should know about this account…" },
  ];

  const defaultColumns = [
    { key: "name", header: "Name", sortable: true, render: (c: Company) => <span className="font-medium">{c.name}</span> },
    { key: "industry", header: "Industry", sortable: true },
    { key: "city", header: "City" },
    { key: "website", header: "Website", render: (c: Company) => c.website || "—" },
    {
      key: "owner",
      header: "Manager",
      render: (c: Company) =>
        c.owner ? (
          <span className="flex items-center gap-2">
            <Avatar first={c.owner.first_name} last={c.owner.last_name} size={22} />
            {fullName(c.owner)}
          </span>
        ) : (
          "—"
        ),
    },
    { key: "created_at", header: "Created", sortable: true, render: (c: Company) => formatDate(c.created_at) },
  ];

  // Every remaining company field, selectable when building a custom view.
  const extraColumns = [
    { key: "email", header: "Email", render: (c: Company) => c.email || "—" },
    { key: "phone", header: "Phone", render: (c: Company) => c.phone || "—" },
    { key: "gst_number", header: "GST number", render: (c: Company) => c.gst_number || "—" },
    {
      key: "address",
      header: "Street address",
      render: (c: Company) => (
        <span className="block max-w-52 truncate" title={c.address ?? ""}>
          {c.address || "—"}
        </span>
      ),
    },
    { key: "state", header: "State" },
    { key: "country", header: "Country" },
    { key: "postal_code", header: "Postal code" },
    {
      key: "tags",
      header: "Tags",
      render: (c: Company) =>
        c.tags?.length ? (
          <span className="flex max-w-52 flex-wrap gap-1">
            {c.tags.map((t) => (
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
      render: (c: Company) => (
        <span className="block max-w-64 truncate" title={c.notes ?? ""}>
          {c.notes || "—"}
        </span>
      ),
    },
  ];

  return (
    <CrudPage<Company>
      title="Companies"
      singular="Company"
      endpoint="/companies"
      module="companies"
      ioEntity="companies"
      filterFields={filterFields}
      schema={schema}
      defaults={defaults}
      fields={fields}
      toForm={(c) => ({ ...c, owner_id: c.owner_id ?? "" })}
      searchPlaceholder="Search companies…"
      columns={defaultColumns}
      allColumns={[...defaultColumns, ...extraColumns]}
    />
  );
}
