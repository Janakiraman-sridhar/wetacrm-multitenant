import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { FileDown, ListFilter, Plus, Receipt, Search, Send, ShieldCheck, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import { BillingForm, BillingFormValues, emptyBillingValues } from "@/components/BillingForm";
import { useViewColumns } from "@/components/CrudPage";
import { Column, DataTable } from "@/components/DataTable";
import { FiltersBar } from "@/components/FiltersBar";
import { ImportExport } from "@/components/ImportExport";
import {
  InsuranceQuoteForm, InsuranceQuoteValues, emptyInsuranceQuote, fromInsuranceQuote,
  toInsurancePayload,
} from "@/components/InsuranceQuoteForm";
import { ConfirmDialog, Modal } from "@/components/Modal";
import { StatusBadge } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { API_URL, api, errorMessage, tokenStore } from "@/lib/api";
import { ActiveFilter, countActive, FilterFieldDef, serializeFilters } from "@/lib/filters";
import { formatDate, formatMoney } from "@/lib/format";
import { useHasModule } from "@/lib/modules";
import { useCompanyOptions, useContactOptions, useProducts } from "@/lib/options";
import type { Page, Quotation } from "@/types";

const QUOTE_STATUS = ["draft", "sent", "accepted", "declined", "converted"].map((s) => ({
  value: s,
  label: s[0].toUpperCase() + s.slice(1),
}));

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
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<ActiveFilter[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Quotation | null>(null);
  const [deleting, setDeleting] = useState<Quotation | null>(null);
  const [insuranceOpen, setInsuranceOpen] = useState(false);
  const [converting, setConverting] = useState<Quotation | null>(null);
  const [policyNumber, setPolicyNumber] = useState("");

  const hasModule = useHasModule();
  const insuranceTenant = hasModule("policies");

  const companies = useCompanyOptions();
  const contacts = useContactOptions();
  const products = useProducts();

  const filterFields: FilterFieldDef[] = [
    { key: "status", label: "Status", type: "select", options: QUOTE_STATUS },
    { key: "company_id", label: "Company", type: "select", options: companies },
    { key: "total", label: "Total", type: "number" },
    { key: "issue_date", label: "Issue date", type: "date" },
    { key: "valid_until", label: "Valid until", type: "date" },
    { key: "created_at", label: "Created date", type: "date" },
  ];
  const filtersParam = useMemo(() => serializeFilters(filters), [filters]);
  const activeFilterCount = countActive(filters);

  const query = useQuery({
    queryKey: ["/quotations", page, pageSize, search, filtersParam],
    queryFn: async () =>
      (await api.get<Page<Quotation>>("/quotations", { params: { page, page_size: pageSize, search: search || undefined, sort: "-created_at", filters: filtersParam } })).data,
    placeholderData: keepPreviousData,
  });

  const form = useForm<BillingFormValues>({ defaultValues: emptyBillingValues });
  const insuranceForm = useForm<InsuranceQuoteValues>({ defaultValues: emptyInsuranceQuote });

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

  const saveInsuranceMutation = useMutation({
    mutationFn: async (v: InsuranceQuoteValues) => {
      const payload = toInsurancePayload(v);
      if (editing) return (await api.patch(`/quotations/${editing.id}`, payload)).data;
      return (await api.post("/quotations", payload)).data;
    },
    onSuccess: () => {
      toast(editing ? "Quotation updated" : "Insurance quotation created");
      setInsuranceOpen(false);
      queryClient.invalidateQueries({ queryKey: ["/quotations"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const convertToPolicyMutation = useMutation({
    mutationFn: async ({ q, number }: { q: Quotation; number: string }) =>
      (await api.post(`/quotations/${q.id}/convert-to-policy`, { policy_number: number })).data,
    onSuccess: (policy) => {
      toast(`Policy ${policy.policy_number} booked`);
      setConverting(null);
      setPolicyNumber("");
      queryClient.invalidateQueries({ queryKey: ["/quotations"] });
      queryClient.invalidateQueries({ queryKey: ["/policies"] });
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

  const openInsuranceCreate = () => {
    setEditing(null);
    insuranceForm.reset(emptyInsuranceQuote);
    setInsuranceOpen(true);
  };

  const openEdit = (q: Quotation) => {
    if (q.kind === "insurance") {
      setEditing(q);
      insuranceForm.reset(fromInsuranceQuote(q));
      setInsuranceOpen(true);
      return;
    }
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
    {
      key: "company", header: "For",
      render: (q) =>
        q.kind === "insurance" ? (
          <span>
            <span className="block">
              {q.contact ? `${q.contact.first_name} ${q.contact.last_name}`.trim() : "—"}
            </span>
            <span className="block text-xs text-slate-400">
              {(q.insurance?.options?.length ?? 0)} insurer
              {(q.insurance?.options?.length ?? 0) === 1 ? "" : "s"} compared
            </span>
          </span>
        ) : (
          q.company?.name ?? "—"
        ),
    },
    { key: "status", header: "Status", render: (q) => <StatusBadge value={q.status} /> },
    { key: "issue_date", header: "Issued", render: (q) => formatDate(q.issue_date) },
    { key: "valid_until", header: "Valid until", render: (q) => formatDate(q.valid_until) },
    { key: "total", header: "Total", render: (q) => <span className="font-semibold">{formatMoney(q.total, q.currency)}</span> },
  ];

  const extraColumns: Column<Quotation>[] = [
    { key: "contact", header: "Contact", render: (q) => (q.contact ? `${q.contact.first_name} ${q.contact.last_name}`.trim() : "—") },
    { key: "subtotal", header: "Subtotal", render: (q) => formatMoney(q.subtotal, q.currency) },
    { key: "tax_total", header: "Tax", render: (q) => formatMoney(q.tax_total, q.currency) },
    { key: "discount", header: "Discount", render: (q) => formatMoney(q.discount, q.currency) },
    { key: "items", header: "Line items", render: (q) => `${q.items.length}` },
    {
      key: "notes",
      header: "Notes",
      render: (q) => (
        <span className="block max-w-64 truncate" title={q.notes ?? ""}>
          {q.notes || "—"}
        </span>
      ),
    },
    { key: "created_at", header: "Created", render: (q) => formatDate(q.created_at) },
  ];

  const { visibleColumns, viewsControl } = useViewColumns("quotations", columns, [...columns, ...extraColumns]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Quotations</h1>
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
            entity="quotations"
            module="quotations"
            label="Quotations"
            filtered={activeFilterCount > 0}
            exportParams={{ filters: filtersParam }}
          />
          {viewsControl}
          <div className="relative w-full min-w-0 sm:w-auto">
            <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input w-full !pl-8 sm:w-56"
              placeholder="Search quotations…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          {canWrite && insuranceTenant && (
            <button className="btn-secondary" onClick={openInsuranceCreate} title="Compare insurers for one risk">
              <ShieldCheck size={15} /> Insurance quote
            </button>
          )}
          {canWrite && (
            <button className="btn-primary" onClick={openCreate}>
              <Plus size={16} /> New Quotation
            </button>
          )}
        </div>
      </div>

      {showFilters || activeFilterCount > 0 ? (
        <div className="shrink-0">
          <FiltersBar fields={filterFields} value={filters} onChange={(f) => { setFilters(f); setPage(1); }} />
        </div>
      ) : null}

      <DataTable<Quotation>
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
        actions={(q) => (
          <div className="flex justify-end gap-1">
            <button
              className="btn-ghost !p-1.5"
              title={q.kind === "insurance" ? "Comparison sheet" : "View PDF"}
              onClick={() =>
                openAuthedPdf(
                  q.kind === "insurance"
                    ? `/quotations/${q.id}/comparison.pdf`
                    : `/quotations/${q.id}/pdf`
                )
              }
            >
              <FileDown size={14} />
            </button>
            {canWrite && q.kind !== "insurance" && (
              <button className="btn-ghost !p-1.5" title="Send by email" onClick={() => sendMutation.mutate(q)}>
                <Send size={14} />
              </button>
            )}
            {q.kind === "insurance"
              ? hasPerm("policies:write") && !q.policy_id && (
                  <button
                    className="btn-ghost !p-1.5 text-emerald-600"
                    title="Book as a policy"
                    onClick={() => {
                      setConverting(q);
                      setPolicyNumber("");
                    }}
                  >
                    <ShieldCheck size={14} />
                  </button>
                )
              : hasModule("invoices") && hasPerm("invoices:write") && q.status !== "converted" && (
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

      <Modal
        open={insuranceOpen}
        onClose={() => setInsuranceOpen(false)}
        title={editing ? `Edit ${editing.number}` : "New insurance quotation"}
        wide
      >
        <InsuranceQuoteForm
          form={insuranceForm}
          onSubmit={(v) => saveInsuranceMutation.mutate(v)}
          busy={saveInsuranceMutation.isPending}
          contacts={contacts}
          onCancel={() => setInsuranceOpen(false)}
        />
      </Modal>

      <Modal open={!!converting} onClose={() => setConverting(null)} title="Book as a policy">
        <div className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            The selected option on {converting?.number} becomes a policy. The policy number
            comes from the insurer, so enter the one on the document — the rest is carried
            across from the quotation.
          </p>
          <div>
            <label className="label">Policy number</label>
            <input
              className="input"
              autoFocus
              value={policyNumber}
              onChange={(e) => setPolicyNumber(e.target.value)}
              placeholder="As printed on the policy"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setConverting(null)}>
              Cancel
            </button>
            <button
              className="btn-primary"
              disabled={!policyNumber.trim() || convertToPolicyMutation.isPending}
              onClick={() =>
                converting &&
                convertToPolicyMutation.mutate({ q: converting, number: policyNumber.trim() })
              }
            >
              {convertToPolicyMutation.isPending ? "Booking…" : "Book policy"}
            </button>
          </div>
        </div>
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
