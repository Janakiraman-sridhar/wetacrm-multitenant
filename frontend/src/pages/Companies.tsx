import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { Avatar } from "@/components/ui";
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

  const fields: FieldDef[] = [
    { name: "name", label: "Company name", colSpan: 2 },
    { name: "industry", label: "Industry" },
    { name: "website", label: "Website", placeholder: "https://…" },
    { name: "email", label: "Email", type: "email" },
    { name: "phone", label: "Phone" },
    { name: "gst_number", label: "GST number" },
    { name: "owner_id", label: "Account manager", type: "select", options: users },
    { name: "address", label: "Address", type: "textarea", colSpan: 2 },
    { name: "city", label: "City" },
    { name: "state", label: "State" },
    { name: "country", label: "Country" },
    { name: "postal_code", label: "Postal code" },
    { name: "notes", label: "Notes", type: "textarea", colSpan: 2 },
  ];

  return (
    <CrudPage<Company>
      title="Companies"
      singular="Company"
      endpoint="/companies"
      module="companies"
      schema={schema}
      defaults={defaults}
      fields={fields}
      toForm={(c) => ({ ...c, owner_id: c.owner_id ?? "" })}
      searchPlaceholder="Search companies…"
      columns={[
        { key: "name", header: "Name", sortable: true, render: (c) => <span className="font-medium">{c.name}</span> },
        { key: "industry", header: "Industry", sortable: true },
        { key: "city", header: "City" },
        { key: "website", header: "Website", render: (c) => c.website || "—" },
        {
          key: "owner",
          header: "Manager",
          render: (c) =>
            c.owner ? (
              <span className="flex items-center gap-2">
                <Avatar first={c.owner.first_name} last={c.owner.last_name} size={22} />
                {fullName(c.owner)}
              </span>
            ) : (
              "—"
            ),
        },
        { key: "created_at", header: "Created", sortable: true, render: (c) => formatDate(c.created_at) },
      ]}
    />
  );
}
