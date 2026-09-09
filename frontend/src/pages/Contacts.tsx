import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Building2, Globe, IdCard, Mail, MapPin, Paperclip, Phone, UserRound } from "lucide-react";
import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { CustomerChip } from "@/components/CustomerChip";
import { NomineeFields } from "@/components/NomineeFields";
import { RecordPanel } from "@/components/RecordPanel";
import { Avatar } from "@/components/ui";
import { api } from "@/lib/api";
import { FilterFieldDef } from "@/lib/filters";
import { formatDate, fullName } from "@/lib/format";
import { useCompanyOptions, useTagOptions, useUserOptions } from "@/lib/options";
import { optNum, optStr, reqStr } from "@/lib/zh";
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
  tags: z.array(z.string()).default([]),

  // Insurance customer fields. Optional here and validated server-side, so the
  // same page serves a general CRM tenant that never fills them in.
  date_of_birth: optStr,
  gender: optStr,
  marital_status: optStr,
  occupation: optStr,
  annual_income: optNum,
  mobile: optStr,
  alt_mobile: optStr,
  alt_email: optStr,
  address_line: optStr,
  pincode: optStr,
  city: optStr,
  state: optStr,
  pan: optStr,
  aadhaar: optStr,
  stage: optStr,
  referred_by_type: optStr,
  referred_by_name: optStr,
  products_of_interest: z.array(z.string()).default([]),

  nominees: z
    .array(
      z.object({
        name: z.string(),
        relation: optStr,
        age: optNum,
        share_percent: optNum,
        appointee_name: optStr,
        appointee_relation: optStr,
      })
    )
    .default([]),
})
  // The insurer's two rules, checked here so the agent is told which row is wrong
  // rather than being handed a refusal about the set on save. The API enforces both
  // regardless — this is a courtesy, not the guard.
  .superRefine((values, ctx) => {
    const rows = (values.nominees ?? []).filter((n) => (n.name ?? "").trim());
    if (!rows.length) return;
    const total = rows.reduce((sum, n) => sum + Number(n.share_percent || 0), 0);
    if (total !== 100) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["nominees"],
        message: `Nominee shares total ${total}% — they must add up to 100.`,
      });
    }
    rows.forEach((n) => {
      if (Number(n.share_percent || 0) < 1) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["nominees"],
          message: `${n.name || "That nominee"} has no share — give them at least 1%, or remove them.`,
        });
      }
      if (n.age != null && Number(n.age) < 18 && !(n.appointee_name ?? "").trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["nominees"],
          message: `${n.name || "That nominee"} is under 18 and needs an appointee.`,
        });
      }
    });
  });

const defaults = {
  first_name: "", last_name: "", position: "", company_id: "", email_primary: "",
  email_secondary: "", phone_primary: "", phone_secondary: "", linkedin: "", twitter: "",
  notes: "", owner_id: "", tags: [] as string[],
  date_of_birth: "", gender: "", marital_status: "", occupation: "", annual_income: "",
  mobile: "", alt_mobile: "", alt_email: "", address_line: "", pincode: "", city: "", state: "",
  pan: "", aadhaar: "", stage: "", referred_by_type: "", referred_by_name: "",
  products_of_interest: [] as string[],
  nominees: [] as any[],
};

const GENDERS = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
  { value: "other", label: "Other" },
  { value: "prefer_not_to_say", label: "Prefer not to say" },
];

const MARITAL_STATUSES = [
  { value: "single", label: "Single" },
  { value: "married", label: "Married" },
  { value: "widowed", label: "Widowed" },
  { value: "divorced", label: "Divorced" },
];

const REFERRAL_TYPES = [
  { value: "customer", label: "Existing customer" },
  { value: "staff", label: "Staff" },
  { value: "external", label: "External referrer" },
  { value: "campaign", label: "Campaign" },
  { value: "walk_in", label: "Walk-in" },
];

const CUSTOMER_STAGES = [
  "Prospect", "Contacted", "Documents pending", "Policy issued",
  "Active", "Renewal due", "Lapsed", "Dormant",
].map((name) => ({ value: name, label: name }));

/** Product lines an agent can flag interest in, loans included. */
const PRODUCT_INTERESTS = [
  "Motor", "Health", "Life", "Travel", "Personal Accident", "Fire / Property",
  "Home Loan", "Personal Loan", "Vehicle Loan", "Business Loan", "Loan Against Property",
].map((name) => ({ value: name, label: name }));

/** The form uses flat fields; convert to/from the API's array-based shape. */
function toApi(values: any) {
  const { email_primary, email_secondary, phone_primary, phone_secondary, linkedin, twitter, ...rest } = values;
  return {
    ...rest,
    // A row someone started and abandoned would fail the share check and block the
    // save, so an unnamed nominee is not a nominee.
    nominees: (rest.nominees ?? [])
      .filter((n: any) => (n.name ?? "").trim())
      .map((n: any) => ({
        ...n,
        age: n.age === "" || n.age == null ? null : Number(n.age),
        share_percent: Number(n.share_percent || 0),
      })),
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
    // Name, number and a way to message them — so an agent never opens a record
    // just to find the phone number.
    render: (c: Contact) => (
      <span className="font-medium">
        <CustomerChip person={c} compact />
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
  /** The record whose notes, files and history are open, if any. */
  const [panel, setPanel] = useState<{ id: string; title: string; subtitle?: string } | null>(null);
  const users = useUserOptions();
  const companies = useCompanyOptions();
  const tags = useTagOptions();

  const filterFields: FilterFieldDef[] = [
    { key: "position", label: "Position", type: "text" },
    { key: "company_id", label: "Company", type: "select", options: companies },
    { key: "owner_id", label: "Owner", type: "select", options: users },
    { key: "created_at", label: "Created date", type: "date" },
  ];

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
    { name: "tags", label: "Products / services (tags)", type: "multiselect", options: tags, colSpan: 2, placeholder: "Tag products or services…" },
    { name: "notes", label: "Notes", type: "textarea", colSpan: 2 },

    // --- customer details ---------------------------------------------------
    { name: "mobile", label: "Mobile", section: "Customer details", placeholder: "98765 43210" },
    { name: "alt_mobile", label: "Alternate mobile", section: "Customer details" },
    { name: "date_of_birth", label: "Date of birth", type: "date", section: "Customer details" },
    { name: "gender", label: "Gender", type: "select", options: GENDERS, section: "Customer details" },
    { name: "marital_status", label: "Marital status", type: "select", options: MARITAL_STATUSES, section: "Customer details" },
    { name: "occupation", label: "Occupation", section: "Customer details" },
    { name: "annual_income", label: "Annual income", type: "number", section: "Customer details" },
    { name: "alt_email", label: "Alternate email", type: "email", section: "Customer details" },
    { name: "stage", label: "Stage", type: "select", options: CUSTOMER_STAGES, section: "Customer details" },
    {
      name: "products_of_interest",
      label: "Interested in",
      type: "multiselect",
      options: PRODUCT_INTERESTS,
      colSpan: 2,
      section: "Customer details",
      placeholder: "Insurance and loan products…",
    },

    // --- KYC ----------------------------------------------------------------
    {
      name: "pan",
      label: "PAN",
      section: "KYC",
      placeholder: "ABCDE1234F",
      after: () => (
        <p className="text-xs text-slate-400">
          Stored encrypted and shown masked. Viewing the full number is recorded.
        </p>
      ),
    },
    { name: "aadhaar", label: "Aadhaar", section: "KYC", placeholder: "1234 5678 9012" },

    // --- address ------------------------------------------------------------
    { name: "address_line", label: "Address", type: "textarea", colSpan: 2, section: "Address" },
    { name: "pincode", label: "Pincode", section: "Address", placeholder: "600001" },
    { name: "city", label: "City", section: "Address" },
    { name: "state", label: "State", section: "Address" },

    // --- referral -----------------------------------------------------------
    {
      name: "nominees",
      label: "Nominees",
      section: "Nominees",
      colSpan: 2,
      render: ({ control, name }) => <NomineeFields control={control} name={name} />,
    },

    { name: "referred_by_type", label: "Referred by", type: "select", options: REFERRAL_TYPES, section: "Referral" },
    { name: "referred_by_name", label: "Referrer name", section: "Referral" },
  ];

  return (
    <>
    <CrudPage<Contact>
      title="Contacts"
      endpoint="/contacts"
      module="contacts"
      ioEntity="contacts"
      filterFields={filterFields}
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
        tags: c.tags ?? [],
        date_of_birth: c.date_of_birth ?? "",
        gender: c.gender ?? "",
        marital_status: c.marital_status ?? "",
        occupation: c.occupation ?? "",
        annual_income: c.annual_income ?? "",
        mobile: c.mobile ?? "",
        alt_mobile: c.alt_mobile ?? "",
        alt_email: c.alt_email ?? "",
        address_line: c.address_line ?? "",
        pincode: c.pincode ?? "",
        city: c.city ?? "",
        state: c.state ?? "",
        stage: c.stage ?? "",
        nominees: (c.nominees ?? []).map((n) => ({
          name: n.name,
          relation: n.relation ?? "",
          age: n.age ?? "",
          share_percent: n.share_percent ?? 100,
          appointee_name: n.appointee_name ?? "",
          appointee_relation: n.appointee_relation ?? "",
        })),
        referred_by_type: c.referred_by_type ?? "",
        referred_by_name: c.referred_by_name ?? "",
        products_of_interest: c.products_of_interest ?? [],
        // Identity is write-only: the form starts blank so an unchanged save does
        // not overwrite what is stored, and the masked value is shown in the table.
        pan: "",
        aadhaar: "",
      })}
      searchPlaceholder="Search contacts…"
      columns={contactDefaultColumns}
      allColumns={[...contactDefaultColumns, ...contactExtraColumns]}
      rowActions={(row) => (
        <button
          className="btn-ghost !p-1.5"
          title="Notes, files and history"
          onClick={() =>
            setPanel({
              id: row.id,
              title: [row.first_name, row.last_name].filter(Boolean).join(" "),
              subtitle: row.mobile ?? row.emails?.[0] ?? undefined,
            })
          }
        >
          <Paperclip size={15} />
        </button>
      )}
    />

    <RecordPanel
      open={!!panel}
      onClose={() => setPanel(null)}
      entityType="contact"
      entityId={panel?.id ?? ""}
      title={panel?.title ?? ""}
      subtitle={panel?.subtitle}
    />
    </>
  );
}
