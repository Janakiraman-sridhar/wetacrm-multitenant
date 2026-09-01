import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { formatDate, formatMoney } from "@/lib/format";
import { numDefault, optNum, optStr, reqStr } from "@/lib/zh";
import type { Product } from "@/types";

const schema = z.object({
  name: reqStr("Product name is required"),
  sku: optStr,
  category: optStr,
  unit_price: numDefault(0),
  currency: z.string().default("INR"),
  tax_rate: numDefault(0),
  stock_qty: optNum,
  is_active: z.boolean().default(true),
  description: optStr,
});

const defaults = {
  name: "", sku: "", category: "", unit_price: 0, currency: "INR",
  tax_rate: 0, stock_qty: "", is_active: true, description: "",
};

const productDefaultColumns = [
  { key: "name", header: "Product", sortable: true, render: (p: Product) => <span className="font-medium">{p.name}</span> },
  { key: "sku", header: "SKU" },
  { key: "category", header: "Category", sortable: true },
  { key: "unit_price", header: "Price", sortable: true, render: (p: Product) => formatMoney(p.unit_price, p.currency) },
  { key: "tax_rate", header: "Tax %", render: (p: Product) => `${p.tax_rate}%` },
  { key: "stock_qty", header: "Stock", render: (p: Product) => (p.stock_qty ?? "—") as any },
  {
    key: "is_active",
    header: "Status",
    render: (p: Product) => (
      <span className={`badge ${p.is_active ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300" : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"}`}>
        {p.is_active ? "Active" : "Inactive"}
      </span>
    ),
  },
];

const productExtraColumns = [
  { key: "currency", header: "Currency" },
  {
    key: "description",
    header: "Description",
    render: (p: Product) => (
      <span className="block max-w-64 truncate" title={p.description ?? ""}>
        {p.description || "—"}
      </span>
    ),
  },
  { key: "created_at", header: "Created", sortable: true, render: (p: Product) => formatDate(p.created_at) },
];

export default function Products() {
  const fields: FieldDef[] = [
    { name: "name", label: "Product name", colSpan: 2 },
    { name: "sku", label: "SKU" },
    { name: "category", label: "Category" },
    { name: "unit_price", label: "Unit price", type: "number", step: "0.01" },
    { name: "tax_rate", label: "Tax rate (%)", type: "number", step: "0.01" },
    { name: "currency", label: "Currency" },
    { name: "stock_qty", label: "Stock (optional)", type: "number" },
    { name: "description", label: "Description", type: "textarea", colSpan: 2 },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];

  return (
    <CrudPage<Product>
      title="Products"
      endpoint="/products"
      module="products"
      schema={schema}
      defaults={defaults}
      fields={fields}
      toForm={(p) => ({
        ...defaults,
        ...p,
        unit_price: Number(p.unit_price),
        tax_rate: Number(p.tax_rate),
        stock_qty: p.stock_qty ?? "",
      })}
      searchPlaceholder="Search products…"
      columns={productDefaultColumns}
      allColumns={[...productDefaultColumns, ...productExtraColumns]}
    />
  );
}
