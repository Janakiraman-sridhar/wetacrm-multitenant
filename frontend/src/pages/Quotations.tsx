import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileDown, Plus, Receipt, Search, Send, Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { BillingForm, BillingFormValues, emptyBillingValues } from "@/components/BillingForm";
import { Column, DataTable } from "@/components/DataTable";
import { ConfirmDialog, Modal } from "@/components/Modal";
import { StatusBadge } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { API_URL, api, errorMessage, tokenStore } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { useCompanyOptions, useContactOptions, useProducts } from "@/lib/options";
import type { Page, Quotation } from "@/types";

export async function openAuthedPdf(path: string) {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    headers: { Authorization: `Bearer ${tokenStore.access}` },
  });
  const blob = await res.blob();
  window.open(URL.createObjectURL(blob), "_blank");
}

export default function Quotations() {
  const { hasPerm } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Quotation | null>(null);
  const [deleting, setDeleting] = useState<Quotation | null>(null);

  const companies = useCompanyOptions();
  const contacts = useContactOptions();
  const products = useProducts();

  const query = useQuery({
    queryKey: ["/quotations", page, search],
    queryFn: async () =>
      (await api.get<Page<Quotation>>("/quotations", { params: { page, page_size: 20, search: search || undefined, sort: "-created_at" } })).data,
    placeholderData: keepPreviousData,
  });

  const form = useForm<BillingFormValues>({ defaultValues: emptyBillingValues });

  const toApi = (v: BillingFormValues) => ({
    company_id: v.company_id || null,
    contact_id: v.contact_id || null,
    issue_date: v.issue_date || null,
    valid_until: v.second_date || null,
    currency: v.currency || "INR",
    discount: Number(v.discount) || 0,
    notes: v.notes || null,
    terms: v.terms || null,
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
      if (editing) return (await api.patch(`/quotations/${editing.id}`, toApi(v))).data;
      return (await api.post("/quotations", toApi(v))).data;
    },
    onSuccess: () => {
      toast(editing ? "Quotation updated" : "Quotation created");
      setModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ["/quotations"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const sendMutation = useMutation({
    mutationFn: async (q: Quotation) => (await api.post(`/quotations/${q.id}/send`, {})).data,
    onSuccess: () => {
      toast("Quotation sent by email");
      queryClient.invalidateQueries({ queryKey: ["/quotations"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const convertMutation = useMutation({
    mutationFn: async (q: Quotation) => (await api.post(`/quotations/${q.id}/convert`)).data,
    onSuccess: (invoice) => {
      toast(`Invoice ${invoice.number} created`);
      queryClient.invalidateQueries({ queryKey: ["/quotations"] });
      queryClient.invalidateQueries({ queryKey: ["/invoices"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: async (q: Quotation) => (await api.delete(`/quotations/${q.id}`)).data,
    onSuccess: () => {
      toast("Quotation deleted");
      setDeleting(null);
      queryClient.invalidateQueries({ queryKey: ["/quotations"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const openCreate = () => {
    setEditing(null);
    form.reset(emptyBillingValues);
    setModalOpen(true);
  };

  const openEdit = (q: Quotation) => {
    setEditing(q);
    form.reset({
      company_id: q.company_id ?? "",
      contact_id: q.contact_id ?? "",
      issue_date: q.issue_date ?? "",
      second_date: q.valid_until ?? "",
      currency: q.currency,
      discount: Number(q.discount),
      notes: q.notes ?? "",
      terms: q.terms ?? "",
      items: q.items.length
        ? q.items.map((i) => ({
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

  const canWrite = hasPerm("quotations:write");

  const columns: Column<Quotation>[] = [
    { key: "number", header: "#", render: (q) => <span className="font-mono text-xs">{q.number}</span> },
    { key: "company", header: "Company", render: (q) => q.company?.name ?? "—" },
    { key: "status", header: "Status", render: (q) => <StatusBadge value={q.status} /> },
    { key: "issue_date", header: "Issued", render: (q) => formatDate(q.issue_date) },
    { key: "valid_until", header: "Valid until", render: (q) => formatDate(q.valid_until) },
    { key: "total", header: "Total", render: (q) => <span className="font-semibold">{formatMoney(q.total, q.currency)}</span> },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Quotations</h1>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input w-56 !pl-8"
              placeholder="Search quotations…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          {canWrite && (
            <button className="btn-primary" onClick={openCreate}>
              <Plus size={16} /> New Quotation
            </button>
          )}
        </div>
      </div>

      <DataTable<Quotation>
        fill
        columns={columns}
        rows={query.data?.items ?? []}
        total={query.data?.total ?? 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
        loading={query.isLoading}
        onRowClick={canWrite ? openEdit : undefined}
        actions={(q) => (
          <div className="flex justify-end gap-1">
            <button className="btn-ghost !p-1.5" title="View PDF" onClick={() => openAuthedPdf(`/quotations/${q.id}/pdf`)}>
              <FileDown size={14} />
            </button>
            {canWrite && (
              <button className="btn-ghost !p-1.5" title="Send by email" onClick={() => sendMutation.mutate(q)}>
                <Send size={14} />
              </button>
            )}
            {hasPerm("invoices:write") && q.status !== "converted" && (
              <button className="btn-ghost !p-1.5 text-emerald-600" title="Convert to invoice" onClick={() => convertMutation.mutate(q)}>
                <Receipt size={14} />
              </button>
            )}
            {hasPerm("quotations:delete") && (
              <button className="btn-ghost !p-1.5 text-red-500" title="Delete" onClick={() => setDeleting(q)}>
                <Trash2 size={14} />
              </button>
            )}
          </div>
        )}
      />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? `Edit ${editing.number}` : "New Quotation"} wide>
        <BillingForm
          form={form}
          onSubmit={(v) => saveMutation.mutate(v)}
          busy={saveMutation.isPending}
          companies={companies}
          contacts={contacts}
          products={products}
          secondDateLabel="Valid until"
          showTerms
          onCancel={() => setModalOpen(false)}
        />
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && deleteMutation.mutate(deleting)}
        title="Delete quotation?"
        message={`${deleting?.number} will be permanently removed.`}
        busy={deleteMutation.isPending}
      />
    </div>
  );
}
