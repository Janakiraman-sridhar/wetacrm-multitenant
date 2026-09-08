import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { FileDown, IndianRupee, ListFilter, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import { BillingForm, BillingFormValues, emptyBillingValues } from "@/components/BillingForm";
import { useViewColumns } from "@/components/CrudPage";
import { Column, DataTable } from "@/components/DataTable";
import { FiltersBar } from "@/components/FiltersBar";
import { ImportExport } from "@/components/ImportExport";
import { ConfirmDialog, Modal } from "@/components/Modal";
import { StatusBadge } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { ActiveFilter, countActive, FilterFieldDef, serializeFilters } from "@/lib/filters";
import { formatDate, formatMoney } from "@/lib/format";
import { useCompanyOptions, useContactOptions, useProducts } from "@/lib/options";
import { openAuthedPdf } from "@/pages/Quotations";
import type { Invoice, Page } from "@/types";

const INVOICE_STATUS = ["draft", "sent", "partial", "paid", "overdue", "cancelled"].map((s) => ({
  value: s,
  label: s[0].toUpperCase() + s.slice(1),
}));

export default function Invoices() {
  const { hasPerm } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<ActiveFilter[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Invoice | null>(null);
  const [deleting, setDeleting] = useState<Invoice | null>(null);
  const [paying, setPaying] = useState<Invoice | null>(null);
  const [paymentAmount, setPaymentAmount] = useState("");

  const companies = useCompanyOptions();
  const contacts = useContactOptions();
  const products = useProducts();

  const filterFields: FilterFieldDef[] = [
    { key: "status", label: "Status", type: "select", options: INVOICE_STATUS },
    { key: "company_id", label: "Company", type: "select", options: companies },
    { key: "total", label: "Total", type: "number" },
    { key: "amount_paid", label: "Amount paid", type: "number" },
    { key: "issue_date", label: "Issue date", type: "date" },
    { key: "due_date", label: "Due date", type: "date" },
    { key: "created_at", label: "Created date", type: "date" },
  ];
  const filtersParam = useMemo(() => serializeFilters(filters), [filters]);
  const activeFilterCount = countActive(filters);

  const query = useQuery({
    queryKey: ["/invoices", page, pageSize, search, filtersParam],
    queryFn: async () =>
      (await api.get<Page<Invoice>>("/invoices", { params: { page, page_size: pageSize, search: search || undefined, sort: "-created_at", filters: filtersParam } })).data,
    placeholderData: keepPreviousData,
  });

  const form = useForm<BillingFormValues>({ defaultValues: emptyBillingValues });

  const toApi = (v: BillingFormValues) => ({
    company_id: v.company_id || null,
    contact_id: v.contact_id || null,
    issue_date: v.issue_date || null,
    due_date: v.second_date || null,
    currency: v.currency || "INR",
    discount: Number(v.discount) || 0,
    notes: v.notes || null,
    items: v.items
      .filter((i) => i.name.trim())
      .map((i) => ({
        product_id: i.product_id || null,
        name: i.name,
        quantity: Number(i.quantity) || 1,
        unit_price: Number(i.unit_price) || 0,
        tax_rate: Number(i.tax_rate) || 0,
      })),
  });

  const saveMutation = useMutation({
    mutationFn: async (v: BillingFormValues) => {
      if (editing) return (await api.patch(`/invoices/${editing.id}`, toApi(v))).data;
      return (await api.post("/invoices", toApi(v))).data;
    },
    onSuccess: () => {
      toast(editing ? "Invoice updated" : "Invoice created");
      setModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ["/invoices"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const payMutation = useMutation({
    mutationFn: async (inv: Invoice) =>
      (await api.post(`/invoices/${inv.id}/payments`, { amount: Number(paymentAmount) })).data,
    onSuccess: (inv) => {
      toast(`Payment recorded — status: ${inv.status}`);
      setPaying(null);
      setPaymentAmount("");
      queryClient.invalidateQueries({ queryKey: ["/invoices"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: async (inv: Invoice) => (await api.delete(`/invoices/${inv.id}`)).data,
    onSuccess: () => {
      toast("Invoice deleted");
      setDeleting(null);
      queryClient.invalidateQueries({ queryKey: ["/invoices"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const openCreate = () => {
    setEditing(null);
    form.reset(emptyBillingValues);
    setModalOpen(true);
  };

  const openEdit = (inv: Invoice) => {
    setEditing(inv);
    form.reset({
      company_id: inv.company_id ?? "",
      contact_id: inv.contact_id ?? "",
      issue_date: inv.issue_date ?? "",
      second_date: inv.due_date ?? "",
      currency: inv.currency,
      discount: Number(inv.discount),
      notes: inv.notes ?? "",
      terms: "",
      items: inv.items.length
        ? inv.items.map((i) => ({
            product_id: i.product_id ?? "",
            name: i.name,
            quantity: Number(i.quantity),
            unit_price: Number(i.unit_price),
            tax_rate: Number(i.tax_rate),
          }))
        : emptyBillingValues.items,
    });
    setModalOpen(true);
  };

  const canWrite = hasPerm("invoices:write");

  const columns: Column<Invoice>[] = [
    { key: "number", header: "#", render: (i) => <span className="font-mono text-xs">{i.number}</span> },
    { key: "company", header: "Company", render: (i) => i.company?.name ?? "—" },
    { key: "status", header: "Status", render: (i) => <StatusBadge value={i.status} /> },
    { key: "issue_date", header: "Issued", render: (i) => formatDate(i.issue_date) },
    { key: "due_date", header: "Due", render: (i) => formatDate(i.due_date) },
    { key: "total", header: "Total", render: (i) => <span className="font-semibold">{formatMoney(i.total, i.currency)}</span> },
    { key: "amount_paid", header: "Paid", render: (i) => formatMoney(i.amount_paid, i.currency) },
  ];

  const extraColumns: Column<Invoice>[] = [
    { key: "subtotal", header: "Subtotal", render: (i) => formatMoney(i.subtotal, i.currency) },
    { key: "tax_total", header: "Tax", render: (i) => formatMoney(i.tax_total, i.currency) },
    { key: "discount", header: "Discount", render: (i) => formatMoney(i.discount, i.currency) },
    {
      key: "outstanding",
      header: "Outstanding",
      render: (i) => formatMoney(Math.max(0, i.total - i.amount_paid), i.currency),
    },
    { key: "items", header: "Line items", render: (i) => `${i.items.length}` },
    {
      key: "notes",
      header: "Notes",
      render: (i) => (
        <span className="block max-w-64 truncate" title={i.notes ?? ""}>
          {i.notes || "—"}
        </span>
      ),
    },
    { key: "created_at", header: "Created", render: (i) => formatDate(i.created_at) },
  ];

  const { visibleColumns, viewsControl } = useViewColumns("invoices", columns, [...columns, ...extraColumns]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Invoices</h1>
        <div className="flex flex-wrap items-center gap-2">
          <button
            className={clsx("btn-secondary", (showFilters || activeFilterCount > 0) && "!border-primary-400 !text-primary-700 dark:!border-primary-600 dark:!text-primary-300")}
            onClick={() => setShowFilters((s) => !s)}
          >
            <ListFilter size={15} /> Filters
            {activeFilterCount > 0 && (
              <span className="ml-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary-600 px-1 text-[10px] font-bold text-white">
                {activeFilterCount}
              </span>
            )}
          </button>
          <ImportExport
            entity="invoices"
            module="invoices"
            label="Invoices"
            filtered={activeFilterCount > 0}
            exportParams={{ filters: filtersParam }}
          />
          {viewsControl}
          <div className="relative w-full min-w-0 sm:w-auto">
            <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input w-full !pl-8 sm:w-56"
              placeholder="Search invoices…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          {canWrite && (
            <button className="btn-primary" onClick={openCreate}>
              <Plus size={16} /> New Invoice
            </button>
          )}
        </div>
      </div>

      {showFilters || activeFilterCount > 0 ? (
        <div className="shrink-0">
          <FiltersBar fields={filterFields} value={filters} onChange={(f) => { setFilters(f); setPage(1); }} />
        </div>
      ) : null}

      <DataTable<Invoice>
        fill
        columns={visibleColumns}
        rows={query.data?.items ?? []}
        total={query.data?.total ?? 0}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(size) => {
          setPageSize(size);
          setPage(1);
        }}
        loading={query.isLoading}
        onRowClick={canWrite ? openEdit : undefined}
        actions={(inv) => (
          <div className="flex justify-end gap-1">
            <button className="btn-ghost !p-1.5" title="View PDF" onClick={() => openAuthedPdf(`/invoices/${inv.id}/pdf`)}>
              <FileDown size={14} />
            </button>
            {canWrite && inv.status !== "paid" && inv.status !== "cancelled" && (
              <button
                className="btn-ghost !p-1.5 text-emerald-600"
                title="Record payment"
                onClick={() => {
                  setPaying(inv);
                  setPaymentAmount(String(Math.max(0, inv.total - inv.amount_paid)));
                }}
              >
                <IndianRupee size={14} />
              </button>
            )}
            {hasPerm("invoices:delete") && (
              <button className="btn-ghost !p-1.5 text-red-500" title="Delete" onClick={() => setDeleting(inv)}>
                <Trash2 size={14} />
              </button>
            )}
          </div>
        )}
      />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? `Edit ${editing.number}` : "New Invoice"} wide>
        <BillingForm
          form={form}
          onSubmit={(v) => saveMutation.mutate(v)}
          busy={saveMutation.isPending}
          companies={companies}
          contacts={contacts}
          products={products}
          secondDateLabel="Due date"
          onCancel={() => setModalOpen(false)}
        />
      </Modal>

      <Modal open={!!paying} onClose={() => setPaying(null)} title={`Record payment — ${paying?.number}`}>
        <p className="text-sm text-slate-500">
          Outstanding: <b>{paying ? formatMoney(paying.total - paying.amount_paid, paying.currency) : ""}</b>
        </p>
        <div className="mt-4">
          <label className="label">Amount received</label>
          <input type="number" step="any" className="input" value={paymentAmount} onChange={(e) => setPaymentAmount(e.target.value)} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setPaying(null)}>
            Cancel
          </button>
          <button
            className="btn-primary"
            disabled={payMutation.isPending || !Number(paymentAmount)}
            onClick={() => paying && payMutation.mutate(paying)}
          >
            {payMutation.isPending ? "Saving…" : "Record payment"}
          </button>
        </div>
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && deleteMutation.mutate(deleting)}
        title="Delete invoice?"
        message={`${deleting?.number} will be permanently removed.`}
        busy={deleteMutation.isPending}
      />
    </div>
  );
}
