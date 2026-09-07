import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Plus, Star, Trash2 } from "lucide-react";
import { useFieldArray, useForm } from "react-hook-form";

import type { SelectOption } from "@/components/CrudPage";
import { DatePicker } from "@/components/DatePicker";
import { Select } from "@/components/Select";
import { api } from "@/lib/api";
import type { Master } from "@/types";

/**
 * Quoting several insurers for one risk.
 *
 * The form mirrors the rule the backend enforces: options are **alternatives**, so
 * there is one radio column and one total, not a running sum down the side. An
 * agent looking at this should never be able to read it as a basket.
 */

const PRODUCT_LINES: SelectOption[] = [
  { value: "motor", label: "Motor" },
  { value: "health", label: "Health" },
  { value: "life", label: "Life" },
  { value: "general", label: "General" },
];

export interface QuoteOptionValues {
  insurer_id: string;
  insurer_name: string;
  plan_name: string;
  sum_insured: string;
  idv: string;
  premium_gross: string;
  premium_gst: string;
  add_ons: string;
  features: string;
  claim_settlement_ratio: string;
  recommended: boolean;
  selected: boolean;
}

export interface InsuranceQuoteValues {
  contact_id: string;
  issue_date: string;
  valid_until: string;
  product_line: string;
  registration_no: string;
  existing_insurer: string;
  sum_insured: string;
  notes: string;
  terms: string;
  options: QuoteOptionValues[];
}

export const emptyOption: QuoteOptionValues = {
  insurer_id: "", insurer_name: "", plan_name: "", sum_insured: "", idv: "",
  premium_gross: "", premium_gst: "", add_ons: "", features: "",
  claim_settlement_ratio: "", recommended: false, selected: false,
};

export const emptyInsuranceQuote: InsuranceQuoteValues = {
  contact_id: "", issue_date: "", valid_until: "", product_line: "motor",
  registration_no: "", existing_insurer: "", sum_insured: "", notes: "", terms: "",
  options: [{ ...emptyOption }, { ...emptyOption }],
};

const list = (value: string) =>
  value.split(",").map((v) => v.trim()).filter(Boolean);

const joined = (value: unknown) => (Array.isArray(value) ? value.join(", ") : String(value ?? ""));

/** Form values → the API payload. Blank options are dropped, not sent as empties. */
export function toInsurancePayload(v: InsuranceQuoteValues) {
  return {
    kind: "insurance",
    contact_id: v.contact_id || null,
    issue_date: v.issue_date || null,
    valid_until: v.valid_until || null,
    notes: v.notes || null,
    terms: v.terms || null,
    insurance: {
      product_line: v.product_line,
      registration_no: v.registration_no || null,
      existing_insurer: v.existing_insurer || null,
      sum_insured: v.sum_insured || null,
      options: v.options
        .filter((o) => o.insurer_id || o.insurer_name.trim())
        .map((o) => ({
          insurer_id: o.insurer_id || null,
          insurer_name: o.insurer_name || null,
          plan_name: o.plan_name || null,
          sum_insured: o.sum_insured || null,
          idv: o.idv || null,
          premium_gross: o.premium_gross || null,
          premium_gst: o.premium_gst || null,
          add_ons: list(o.add_ons),
          features: list(o.features),
          claim_settlement_ratio: o.claim_settlement_ratio || null,
          recommended: o.recommended,
          selected: o.selected,
        })),
    },
  };
}

/** An existing quotation → form values. */
export function fromInsuranceQuote(q: any): InsuranceQuoteValues {
  const risk = q.insurance ?? {};
  return {
    contact_id: q.contact_id ?? "",
    issue_date: q.issue_date ?? "",
    valid_until: q.valid_until ?? "",
    product_line: risk.product_line ?? "motor",
    registration_no: risk.registration_no ?? "",
    existing_insurer: risk.existing_insurer ?? "",
    sum_insured: risk.sum_insured != null ? String(risk.sum_insured) : "",
    notes: q.notes ?? "",
    terms: q.terms ?? "",
    options: (risk.options ?? []).length
      ? risk.options.map((o: any) => ({
          insurer_id: o.insurer_id ?? "",
          insurer_name: o.insurer_name ?? "",
          plan_name: o.plan_name ?? "",
          sum_insured: o.sum_insured != null ? String(o.sum_insured) : "",
          idv: o.idv != null ? String(o.idv) : "",
          premium_gross: o.premium_gross != null ? String(o.premium_gross) : "",
          premium_gst: o.premium_gst != null ? String(o.premium_gst) : "",
          add_ons: joined(o.add_ons),
          features: joined(o.features),
          claim_settlement_ratio: o.claim_settlement_ratio ?? "",
          recommended: !!o.recommended,
          selected: !!o.selected,
        }))
      : emptyInsuranceQuote.options.map((o) => ({ ...o })),
  };
}

function useInsurers(): Master[] {
  const { data } = useQuery({
    queryKey: ["masters", "insurer"],
    queryFn: async () => (await api.get<Master[]>("/masters", { params: { type: "insurer" } })).data,
    staleTime: 5 * 60_000,
  });
  return data ?? [];
}

export function InsuranceQuoteForm({
  form,
  onSubmit,
  busy,
  contacts,
  onCancel,
}: {
  form: ReturnType<typeof useForm<InsuranceQuoteValues>>;
  onSubmit: (values: InsuranceQuoteValues) => void;
  busy: boolean;
  contacts: SelectOption[];
  onCancel: () => void;
}) {
  const { register, control, handleSubmit, watch, setValue } = form;
  const { fields, append, remove } = useFieldArray({ control, name: "options" });
  const insurers = useInsurers();
  const values = watch();

  const insurerOptions: SelectOption[] = insurers.map((i) => ({ value: i.id, label: i.name }));

  // Exactly one selection, enforced here as well as on the server — a radio the UI
  // lets you tick twice, then the API rejects, is a worse experience than a radio.
  const choose = (index: number) =>
    fields.forEach((_, i) => setValue(`options.${i}.selected`, i === index));

  const chosen = values.options?.findIndex((o) => o.selected) ?? -1;
  const payable = chosen >= 0 ? Number(values.options[chosen]?.premium_gross || 0) : 0;

  const pickInsurer = (index: number, id: string) => {
    setValue(`options.${index}.insurer_id`, id);
    const insurer = insurers.find((i) => i.id === id);
    if (insurer) setValue(`options.${index}.insurer_name`, insurer.name);
  };

  return (
    <form className="space-y-5" onSubmit={handleSubmit(onSubmit)}>
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label className="label">Customer</label>
          <Select
            options={contacts}
            value={values.contact_id}
            onChange={(v) => setValue("contact_id", v)}
            placeholder="Choose a customer"
          />
        </div>
        <div>
          <label className="label">Cover</label>
          <Select
            options={PRODUCT_LINES}
            value={values.product_line}
            onChange={(v) => setValue("product_line", v)}
          />
        </div>
        <div>
          <label className="label">Sum insured</label>
          <input className="input" type="number" step="0.01" {...register("sum_insured")} />
        </div>
        <div>
          <label className="label">
            {values.product_line === "motor" ? "Registration number" : "Existing policy / reference"}
          </label>
          <input className="input" {...register("registration_no")} />
        </div>
        <div>
          <label className="label">Currently insured with</label>
          <input className="input" {...register("existing_insurer")} />
        </div>
        <div>
          <label className="label">Valid until</label>
          <DatePicker
            value={values.valid_until}
            onChange={(v) => setValue("valid_until", v)}
          />
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <div>
            <h3 className="font-semibold">Insurer options</h3>
            <p className="text-xs text-slate-400">
              Competing quotes for the same cover. The customer takes one, so the quotation
              total is the option you tick — not the three added together.
            </p>
          </div>
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={() => append({ ...emptyOption })}
          >
            <Plus size={15} /> Add option
          </button>
        </div>

        <div className="space-y-3">
          {fields.map((field, index) => (
            <div
              key={field.id}
              className={clsx(
                "rounded-xl border p-3 transition-colors",
                values.options?.[index]?.selected
                  ? "border-emerald-400 bg-emerald-50/60 dark:border-emerald-700 dark:bg-emerald-900/20"
                  : "border-slate-200 dark:border-slate-800"
              )}
            >
              <div className="mb-2 flex items-center justify-between gap-2">
                <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
                  <input
                    type="radio"
                    name="selected-option"
                    checked={!!values.options?.[index]?.selected}
                    onChange={() => choose(index)}
                  />
                  Customer takes this one
                </label>
                <div className="flex items-center gap-2">
                  <label className="flex cursor-pointer items-center gap-1.5 text-xs text-amber-600">
                    <input type="checkbox" {...register(`options.${index}.recommended`)} />
                    <Star size={13} /> Recommend
                  </label>
                  {fields.length > 1 && (
                    <button
                      type="button"
                      className="btn-ghost !p-1.5 text-red-500"
                      onClick={() => remove(index)}
                      title="Remove option"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <div className="col-span-2 md:col-span-1">
                  <label className="label">Insurer</label>
                  {insurerOptions.length ? (
                    <Select
                      options={insurerOptions}
                      value={values.options?.[index]?.insurer_id ?? ""}
                      onChange={(v) => pickInsurer(index, v)}
                      placeholder="Choose"
                    />
                  ) : (
                    <input className="input" placeholder="Insurer name" {...register(`options.${index}.insurer_name`)} />
                  )}
                </div>
                <div>
                  <label className="label">Plan</label>
                  <input className="input" {...register(`options.${index}.plan_name`)} />
                </div>
                <div>
                  <label className="label">Premium payable</label>
                  <input className="input" type="number" step="0.01" {...register(`options.${index}.premium_gross`)} />
                </div>
                <div>
                  <label className="label">of which GST</label>
                  <input className="input" type="number" step="0.01" {...register(`options.${index}.premium_gst`)} />
                </div>
                <div>
                  <label className="label">{values.product_line === "motor" ? "IDV" : "Sum insured"}</label>
                  <input
                    className="input"
                    type="number"
                    step="0.01"
                    {...register(values.product_line === "motor" ? `options.${index}.idv` : `options.${index}.sum_insured`)}
                  />
                </div>
                <div>
                  <label className="label">Claim settlement</label>
                  <input className="input" placeholder="98.1%" {...register(`options.${index}.claim_settlement_ratio`)} />
                </div>
                <div className="col-span-2">
                  <label className="label">Add-ons</label>
                  <input className="input" placeholder="Zero depreciation, Engine protect" {...register(`options.${index}.add_ons`)} />
                </div>
                <div className="col-span-2 md:col-span-4">
                  <label className="label">Highlights</label>
                  <input className="input" placeholder="Cashless at 8000+ garages, Doorstep pickup" {...register(`options.${index}.features`)} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="label">Notes</label>
          <textarea className="input" rows={2} {...register("notes")} />
        </div>
        <div>
          <label className="label">Terms</label>
          <textarea className="input" rows={2} {...register("terms")} />
        </div>
      </section>

      <div className="flex items-center justify-between border-t border-slate-200 pt-3 dark:border-slate-800">
        <p className="text-sm">
          {chosen >= 0 ? (
            <>
              <span className="text-slate-400">Quotation total (selected option): </span>
              <span className="font-semibold">₹{payable.toLocaleString("en-IN")}</span>
            </>
          ) : (
            <span className="text-slate-400">Tick the option the customer is taking.</span>
          )}
        </p>
        <div className="flex gap-2">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Saving…" : "Save quotation"}
          </button>
        </div>
      </div>
    </form>
  );
}
