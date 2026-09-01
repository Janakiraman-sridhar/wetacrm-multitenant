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
