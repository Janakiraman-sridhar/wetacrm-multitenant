import { useQuery } from "@tanstack/react-query";
import { Building2, Globe, IdCard, Mail, MapPin, Phone, UserRound } from "lucide-react";
import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { Avatar } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, fullName } from "@/lib/format";
import { useCompanyOptions, useUserOptions } from "@/lib/options";
import { optStr, reqStr } from "@/lib/zh";
import type { Company, Contact } from "@/types";

/** Live preview of the selected company, pulled from the Companies module. */
function CompanyPreview({ companyId }: { companyId?: string | null }) {
  const { data: company, isLoading } = useQuery({
    queryKey: ["company-detail", companyId],
    queryFn: async () => (await api.get<Company>(`/companies/${companyId}`)).data,
    enabled: !!companyId,
    staleTime: 30_000,
  });

  if (!companyId) return null;

  if (isLoading || !company) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-800/40">
        <div className="h-3.5 w-40 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
        <div className="mt-2.5 h-3 w-64 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
      </div>
    );
  }

  const location = [company.city, company.state, company.country].filter(Boolean).join(", ");
  const items = [
    { icon: Globe, label: "Website", value: company.website },
    { icon: Mail, label: "Email", value: company.email },
    { icon: Phone, label: "Phone", value: company.phone },
    { icon: MapPin, label: "Location", value: location },
    { icon: IdCard, label: "GST", value: company.gst_number },
  ].filter((i) => i.value);

  return (
    <div className="rounded-xl border border-primary-100 bg-primary-50/60 p-4 dark:border-primary-900/50 dark:bg-primary-900/15">
      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300">
          <Building2 size={15} />
        </span>
        <span className="font-semibold">{company.name}</span>
        {company.industry && (
          <span className="badge bg-white text-slate-600 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700">
            {company.industry}
          </span>
        )}
        <span className="ml-auto text-[11px] uppercase tracking-wide text-slate-400">from Companies</span>
      </div>
      {items.length === 0 && !company.owner ? (
        <p className="text-sm text-slate-400">No further details recorded for this company yet.</p>
      ) : (
        <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
          {items.map(({ icon: Icon, label, value }) => (
            <span key={label} className="flex min-w-0 items-center gap-2 text-slate-600 dark:text-slate-300">
              <Icon size={13} className="shrink-0 text-primary-500" />
              <span className="truncate" title={`${label}: ${value}`}>
                {value}
              </span>
            </span>
          ))}
          {company.owner && (
            <span className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
              <UserRound size={13} className="shrink-0 text-primary-500" />
              <Avatar first={company.owner.first_name} last={company.owner.last_name} size={18} />
              <span className="truncate">{fullName(company.owner)} (account manager)</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

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
    {
      name: "company_id",
      label: "Company",
      type: "select",
      options: companies,
      placeholder: "Link a company…",
      after: (values) => <CompanyPreview companyId={values.company_id} />,
    },
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
