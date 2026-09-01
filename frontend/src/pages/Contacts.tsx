import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { formatDate, fullName } from "@/lib/format";
import { useCompanyOptions, useUserOptions } from "@/lib/options";
import { optStr, reqStr } from "@/lib/zh";
import type { Contact } from "@/types";

const schema = z.object({
  first_name: reqStr("First name is required"),
  last_name: z.string().default(""),
  position: optStr,
  company_id: optStr,
  email_primary: optStr,
  email_secondary: optStr,
  phone_primary: optStr,
  phone_secondary: optStr,
  linkedin: optStr,
  twitter: optStr,
  notes: optStr,
  owner_id: optStr,
});

const defaults = {
  first_name: "", last_name: "", position: "", company_id: "", email_primary: "",
  email_secondary: "", phone_primary: "", phone_secondary: "", linkedin: "", twitter: "",
  notes: "", owner_id: "",
};

/** The form uses flat fields; convert to/from the API's array-based shape. */
function toApi(values: any) {
  const { email_primary, email_secondary, phone_primary, phone_secondary, linkedin, twitter, ...rest } = values;
  return {
    ...rest,
    emails: [email_primary, email_secondary].filter(Boolean),
    phones: [phone_primary, phone_secondary].filter(Boolean),
    social_links: {
      ...(linkedin ? { linkedin } : {}),
      ...(twitter ? { twitter } : {}),
    },
  };
}

const contactDefaultColumns = [
  {
    key: "first_name",
    header: "Name",
    sortable: true,
    render: (c: Contact) => (
      <span className="font-medium">
        {c.first_name} {c.last_name}
      </span>
    ),
  },
  { key: "position", header: "Position" },
  { key: "company", header: "Company", render: (c: Contact) => c.company?.name ?? "—" },
  { key: "emails", header: "Email", render: (c: Contact) => c.emails?.[0] ?? "—" },
  { key: "phones", header: "Phone", render: (c: Contact) => c.phones?.[0] ?? "—" },
  { key: "created_at", header: "Created", sortable: true, render: (c: Contact) => formatDate(c.created_at) },
];

const contactExtraColumns = [
  { key: "email_secondary", header: "Email (secondary)", render: (c: Contact) => c.emails?.[1] ?? "—" },
  { key: "phone_secondary", header: "Phone (secondary)", render: (c: Contact) => c.phones?.[1] ?? "—" },
  { key: "linkedin", header: "LinkedIn", render: (c: Contact) => c.social_links?.linkedin ?? "—" },
  { key: "twitter", header: "X / Twitter", render: (c: Contact) => c.social_links?.twitter ?? "—" },
  { key: "owner", header: "Owner", render: (c: Contact) => fullName(c.owner) },
  {
    key: "tags",
    header: "Tags",
    render: (c: Contact) =>
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
    render: (c: Contact) => (
      <span className="block max-w-64 truncate" title={c.notes ?? ""}>
        {c.notes || "—"}
      </span>
    ),
  },
];

export default function Contacts() {
  const users = useUserOptions();
  const companies = useCompanyOptions();

  const fields: FieldDef[] = [
    { name: "first_name", label: "First name" },
    { name: "last_name", label: "Last name" },
    { name: "position", label: "Position / title" },
    { name: "company_id", label: "Company", type: "select", options: companies },
    { name: "email_primary", label: "Email (primary)", type: "email" },
    { name: "email_secondary", label: "Email (secondary)", type: "email" },
    { name: "phone_primary", label: "Phone (primary)" },
    { name: "phone_secondary", label: "Phone (secondary)" },
    { name: "linkedin", label: "LinkedIn", placeholder: "https://linkedin.com/in/…" },
    { name: "twitter", label: "X / Twitter" },
    { name: "owner_id", label: "Owner", type: "select", options: users },
    { name: "notes", label: "Notes", type: "textarea", colSpan: 2 },
  ];

  return (
    <CrudPage<Contact>
      title="Contacts"
      endpoint="/contacts"
      module="contacts"
      schema={schema.transform(toApi)}
      defaults={defaults}
      fields={fields}
      toForm={(c) => ({
        first_name: c.first_name,
        last_name: c.last_name,
        position: c.position ?? "",
        company_id: c.company_id ?? "",
        email_primary: c.emails?.[0] ?? "",
        email_secondary: c.emails?.[1] ?? "",
        phone_primary: c.phones?.[0] ?? "",
        phone_secondary: c.phones?.[1] ?? "",
        linkedin: c.social_links?.linkedin ?? "",
        twitter: c.social_links?.twitter ?? "",
        notes: c.notes ?? "",
        owner_id: c.owner?.id ?? "",
      })}
      searchPlaceholder="Search contacts…"
      columns={contactDefaultColumns}
      allColumns={[...contactDefaultColumns, ...contactExtraColumns]}
    />
  );
}
