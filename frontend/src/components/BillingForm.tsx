import { Plus, Trash2 } from "lucide-react";
import { Controller, useFieldArray, useForm } from "react-hook-form";

import type { SelectOption } from "@/components/CrudPage";
import { DatePicker } from "@/components/DatePicker";
import { formatMoney } from "@/lib/format";
import type { Product } from "@/types";

export interface BillingFormValues {
  company_id: string;
  contact_id: string;
  issue_date: string;
  second_date: string; // valid_until (quotation) or due_date (invoice)
  currency: string;
  discount: number;
  notes: string;
  terms?: string;
  items: { product_id: string; name: string; quantity: number; unit_price: number; tax_rate: number }[];
}

export const emptyBillingValues: BillingFormValues = {
  company_id: "", contact_id: "", issue_date: "", second_date: "", currency: "INR",
  discount: 0, notes: "", terms: "", items: [{ product_id: "", name: "", quantity: 1, unit_price: 0, tax_rate: 0 }],
};

export function computeTotals(values: BillingFormValues) {
  let subtotal = 0;
  let tax = 0;
  for (const item of values.items) {
    const net = (Number(item.quantity) || 0) * (Number(item.unit_price) || 0);
    subtotal += net;
    tax += (net * (Number(item.tax_rate) || 0)) / 100;
  }
  const total = Math.max(0, subtotal + tax - (Number(values.discount) || 0));
  return { subtotal, tax, total };
}

export function BillingForm({
  form,
  onSubmit,
  busy,
  companies,
  contacts,
  products,
  secondDateLabel,
  showTerms,
  onCancel,
}: {
  form: ReturnType<typeof useForm<BillingFormValues>>;
  onSubmit: (values: BillingFormValues) => void;
  busy: boolean;
  companies: SelectOption[];
  contacts: SelectOption[];
  products: Product[];
  secondDateLabel: string;
  showTerms?: boolean;
  onCancel: () => void;
}) {
  const { register, control, handleSubmit, watch, setValue } = form;
  const { fields, append, remove } = useFieldArray({ control, name: "items" });
  const values = watch();
  const totals = computeTotals(values);

  const applyProduct = (index: number, productId: string) => {
    const product = products.find((p) => p.id === productId);
    setValue(`items.${index}.product_id`, productId);
    if (product) {
      setValue(`items.${index}.name`, product.name);
      setValue(`items.${index}.unit_price`, Number(product.unit_price));
      setValue(`items.${index}.tax_rate`, Number(product.tax_rate));
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="label">Company</label>
          <select className="input" {...register("company_id")}>
            <option value="">—</option>
            {companies.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Contact</label>
          <select className="input" {...register("contact_id")}>
            <option value="">—</option>
            {contacts.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Issue date</label>
          <Controller
            control={control}
            name="issue_date"
            render={({ field }) => <DatePicker value={field.value ?? ""} onChange={field.onChange} />}
          />
        </div>
        <div>
          <label className="label">{secondDateLabel}</label>
          <Controller
            control={control}
            name="second_date"
            render={({ field }) => <DatePicker value={field.value ?? ""} onChange={field.onChange} />}
          />
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <label className="label !mb-0">Line items</label>
          <button
            type="button"
            className="btn-ghost !py-1 text-primary-600"
            onClick={() => append({ product_id: "", name: "", quantity: 1, unit_price: 0, tax_rate: 0 })}
          >
            <Plus size={14} /> Add item
          </button>
        </div>
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-400 dark:bg-slate-900">
                <th className="px-2 py-2">Product</th>
                <th className="px-2 py-2">Description</th>
                <th className="w-16 px-2 py-2">Qty</th>
                <th className="w-28 px-2 py-2">Price</th>
                <th className="w-16 px-2 py-2">Tax %</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {fields.map((field, i) => (
                <tr key={field.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-1.5">
                    <select
                      className="input !py-1.5"
                      value={values.items?.[i]?.product_id ?? ""}
                      onChange={(e) => applyProduct(i, e.target.value)}
                    >
                      <option value="">Custom</option>
                      {products.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-1.5">
                    <input className="input !py-1.5" placeholder="Item name" {...register(`items.${i}.name`)} />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      type="number"
                      step="any"
                      className="input !py-1.5"
                      {...register(`items.${i}.quantity`, { valueAsNumber: true })}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      type="number"
                      step="any"
                      className="input !py-1.5"
                      {...register(`items.${i}.unit_price`, { valueAsNumber: true })}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      type="number"
                      step="any"
                      className="input !py-1.5"
                      {...register(`items.${i}.tax_rate`, { valueAsNumber: true })}
                    />
                  </td>
                  <td className="px-1">
                    <button type="button" className="btn-ghost !p-1 text-red-500" onClick={() => remove(i)}>
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-4">
          <div>
            <label className="label">Discount</label>
            <input type="number" step="any" className="input" {...register("discount", { valueAsNumber: true })} />
          </div>
          <div>
            <label className="label">Notes</label>
            <textarea rows={2} className="input" {...register("notes")} />
          </div>
          {showTerms && (
            <div>
              <label className="label">Terms</label>
              <textarea rows={2} className="input" {...register("terms")} />
            </div>
          )}
        </div>
        <div className="card h-fit space-y-1.5 p-4 text-sm">
          <div className="flex justify-between text-slate-500">
            <span>Subtotal</span>
            <span>{formatMoney(totals.subtotal, values.currency)}</span>
          </div>
          <div className="flex justify-between text-slate-500">
            <span>Tax</span>
            <span>{formatMoney(totals.tax, values.currency)}</span>
          </div>
          <div className="flex justify-between text-slate-500">
            <span>Discount</span>
            <span>-{formatMoney(values.discount || 0, values.currency)}</span>
          </div>
          <div className="flex justify-between border-t border-slate-200 pt-1.5 text-base font-bold dark:border-slate-700">
            <span>Total</span>
            <span className="text-primary-600 dark:text-primary-400">{formatMoney(totals.total, values.currency)}</span>
          </div>
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}
