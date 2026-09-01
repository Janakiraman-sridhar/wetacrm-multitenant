import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileDown, IndianRupee, Plus, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { BillingForm, BillingFormValues, emptyBillingValues } from "@/components/BillingForm";
import { Column, DataTable } from "@/components/DataTable";
import { ConfirmDialog, Modal } from "@/components/Modal";
import { StatusBadge } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { useCompanyOptions, useContactOptions, useProducts } from "@/lib/options";
import { openAuthedPdf } from "@/pages/Quotations";
import type { Invoice, Page } from "@/types";

export default function Invoices() {
  const { hasPerm } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Invoice | null>(null);
  const [deleting, setDeleting] = useState<Invoice | null>(null);
  const [paying, setPaying] = useState<Invoice | null>(null);
  const [paymentAmount, setPaymentAmount] = useState("");

  const companies = useCompanyOptions();
  const contacts = useContactOptions();
  const products = useProducts();

  const query = useQuery({
    queryKey: ["/invoices", page, search],
    queryFn: async () =>
      (await api.get<Page<Invoice>>("/invoices", { params: { page, page_size: 20, search: search || undefined, sort: "-created_at" } })).data,
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Invoices</h1>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input w-56 !pl-8"
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

      <DataTable<Invoice>
        columns={columns}
        rows={query.data?.items ?? []}
        total={query.data?.total ?? 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
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
