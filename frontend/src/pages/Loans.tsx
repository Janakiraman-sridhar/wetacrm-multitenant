import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { LayoutGrid, Landmark, List } from "lucide-react";
import { useState } from "react";
import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { CustomerChip } from "@/components/CustomerChip";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { FilterFieldDef } from "@/lib/filters";
import { formatDate } from "@/lib/format";
import { useContactOptions, useUserOptions } from "@/lib/options";
import { useValuePrivacy } from "@/lib/privacy";
import { waTemplates } from "@/lib/whatsapp";
import { optNum, optStr, reqStr } from "@/lib/zh";
import type { Loan, LoanBoardColumn, LoanStats, Master } from "@/types";

const LOAN_TYPES = [
  "Home Loan", "Personal Loan", "Vehicle Loan", "Business Loan",
  "Loan Against Property", "Education Loan",
].map((v) => ({ value: v, label: v }));

const STATUSES = [
  { value: "enquiry", label: "Enquiry" },
  { value: "documents", label: "Documents" },
  { value: "logged_in", label: "Logged in" },
  { value: "sanctioned", label: "Sanctioned" },
  { value: "disbursed", label: "Disbursed" },
  { value: "rejected", label: "Rejected" },
];

const STATUS_STYLES: Record<string, string> = {
  enquiry: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  documents: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  logged_in: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  sanctioned: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  disbursed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  rejected: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

const inr = (value: unknown) => `₹${Number(value || 0).toLocaleString("en-IN")}`;

function useLenders() {
  const { data } = useQuery({
    queryKey: ["masters", "bank"],
    queryFn: async () => (await api.get<Master[]>("/masters", { params: { type: "bank" } })).data,
    staleTime: 5 * 60_000,
  });
  return (data ?? []).map((m) => ({ value: m.id, label: m.name }));
}

const schema = z.object({
  customer_id: reqStr("Choose a customer"),
  loan_type: reqStr("Choose a loan type"),
  lender_id: optStr,
  owner_id: optStr,
  status: optStr,
  amount_requested: optNum,
  amount_sanctioned: optNum,
  tenure_months: optNum,
  interest_rate: optNum,
  payout_percent: optNum,
  actual_payout: optNum,
  applied_on: optStr,
  sanctioned_on: optStr,
  disbursed_on: optStr,
  rejected_reason: optStr,
  remarks: optStr,
});

const defaults = {
  customer_id: "", loan_type: "Home Loan", lender_id: "", owner_id: "", status: "enquiry",
  amount_requested: "", amount_sanctioned: "", tenure_months: "", interest_rate: "",
  payout_percent: "", actual_payout: "", applied_on: "", sanctioned_on: "", disbursed_on: "",
  rejected_reason: "", remarks: "",
};

/** Open cases grouped by stage, with the value sitting in each. */
function LoanBoard() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { show } = useValuePrivacy();

  const { data: columns } = useQuery({
    queryKey: ["loans", "board"],
    queryFn: async () =>
      (await api.get<LoanBoardColumn[]>("/loans/board")).data,
  });

  const move = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) =>
      (await api.patch(`/loans/${id}`, { status })).data,
    onSuccess: () => {
      toast("Case moved");
      queryClient.invalidateQueries({ queryKey: ["loans"] });
      queryClient.invalidateQueries({ queryKey: ["/loans"] });
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  const order = (columns ?? []).map((c) => c.status);

  return (
    <div className="grid min-h-0 flex-1 gap-3 overflow-x-auto md:grid-cols-4">
      {(columns ?? []).map((column, index) => (
        <div key={column.status} className="card flex min-h-0 flex-col p-3">
          <div className="mb-2 flex items-baseline justify-between">
            <h3 className="text-sm font-semibold">{column.label}</h3>
            <span className="text-xs text-slate-400">{column.loans.length}</span>
          </div>
          <p className="mb-2 text-xs text-slate-400">{show(inr(column.value))} requested</p>
          <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto">
            {column.loans.map((loan) => (
              <li key={loan.id} className="rounded-lg border border-slate-200 p-2.5 dark:border-slate-800">
                <p className="truncate text-sm font-medium">{loan.customer?.full_name}</p>
                <p className="text-xs text-slate-400">
                  {loan.loan_type} · {show(inr(loan.amount_requested))}
                </p>
                {loan.lender?.name && (
                  <p className="truncate text-xs text-slate-400">{loan.lender.name}</p>
                )}
                <div className="mt-1.5 flex gap-1">
                  {index > 0 && (
                    <button
                      className="btn-ghost !px-1.5 !py-0.5 text-xs"
                      title={`Move back to ${columns![index - 1].label}`}
                      onClick={() => move.mutate({ id: loan.id, status: order[index - 1] })}
                    >
                      ←
                    </button>
                  )}
                  {index < order.length - 1 && (
                    <button
                      className="btn-ghost !px-1.5 !py-0.5 text-xs"
                      title={`Move on to ${columns![index + 1].label}`}
                      onClick={() => move.mutate({ id: loan.id, status: order[index + 1] })}
                    >
                      →
                    </button>
                  )}
                  <button
                    className="btn-ghost !px-1.5 !py-0.5 text-xs text-emerald-600"
                    title="Mark disbursed"
                    onClick={() => move.mutate({ id: loan.id, status: "disbursed" })}
                  >
                    Disbursed
                  </button>
                </div>
              </li>
            ))}
            {column.loans.length === 0 && (
              <li className="py-6 text-center text-xs text-slate-400">Nothing here.</li>
            )}
          </ul>
        </div>
      ))}
    </div>
  );
}

export default function Loans() {
  const lenders = useLenders();
  const customers = useContactOptions();
  const users = useUserOptions();
  const { show } = useValuePrivacy();
  const [view, setView] = useState<"list" | "board">("list");

  const { data: stats } = useQuery({
    queryKey: ["loans", "stats"],
    queryFn: async () => (await api.get<LoanStats>("/loans/stats")).data,
    staleTime: 60_000,
  });

  const filterFields: FilterFieldDef[] = [
    { key: "loan_type", label: "Loan type", type: "select", options: LOAN_TYPES },
    { key: "status", label: "Status", type: "select", options: STATUSES },
    { key: "lender_id", label: "Lender", type: "select", options: lenders },
    { key: "owner_id", label: "Agent", type: "select", options: users },
    { key: "amount_sanctioned", label: "Sanctioned", type: "number" },
    { key: "applied_on", label: "Applied", type: "date" },
    { key: "disbursed_on", label: "Disbursed", type: "date" },
  ];

  const fields: FieldDef[] = [
    { name: "customer_id", label: "Customer", type: "select", options: customers, section: "Case" },
    { name: "loan_type", label: "Loan type", type: "select", options: LOAN_TYPES, section: "Case" },
    { name: "lender_id", label: "Lender", type: "select", options: lenders, section: "Case" },
    { name: "status", label: "Stage", type: "select", options: STATUSES, section: "Case" },
    { name: "owner_id", label: "Agent", type: "select", options: users, section: "Case" },

    { name: "amount_requested", label: "Amount requested", type: "number", step: "0.01", section: "Amounts" },
    { name: "amount_sanctioned", label: "Amount sanctioned", type: "number", step: "0.01", section: "Amounts" },
    { name: "tenure_months", label: "Tenure (months)", type: "number", section: "Amounts" },
    { name: "interest_rate", label: "Interest rate (%)", type: "number", step: "0.01", section: "Amounts" },
    {
      name: "payout_percent", label: "Payout %", type: "number", step: "0.01", section: "Amounts",
      after: () => (
        <p className="text-xs text-slate-400">
          Applied to the <strong>sanctioned</strong> amount — the expected payout is worked out
          from it, so it never drifts from the numbers beside it.
        </p>
      ),
    },
    { name: "actual_payout", label: "Payout received", type: "number", step: "0.01", section: "Amounts" },

    { name: "applied_on", label: "Applied on", type: "date", section: "Dates" },
    { name: "sanctioned_on", label: "Sanctioned on", type: "date", section: "Dates" },
    { name: "disbursed_on", label: "Disbursed on", type: "date", section: "Dates" },

    { name: "rejected_reason", label: "Rejection reason", section: "Notes" },
    { name: "remarks", label: "Remarks", type: "textarea", colSpan: 2, section: "Notes" },
  ];

  const columns = [
    {
      key: "customer_id", header: "Customer",
      render: (l: Loan) =>
        l.customer ? (
          <CustomerChip person={l.customer} compact message={waTemplates.followUp(l.customer.full_name)} />
        ) : "—",
    },
    {
      key: "loan_type", header: "Loan", sortable: true,
      render: (l: Loan) => (
        <span>
          <span className="block">{l.loan_type}</span>
          <span className="block text-xs text-slate-400">{l.lender?.name ?? "No lender yet"}</span>
        </span>
      ),
    },
    {
      key: "amount_requested", header: "Requested", sortable: true,
      render: (l: Loan) => <span className="tabular-nums">{show(inr(l.amount_requested))}</span>,
    },
    {
      key: "amount_sanctioned", header: "Sanctioned", sortable: true,
      render: (l: Loan) =>
        l.amount_sanctioned ? (
          <span className="tabular-nums">{show(inr(l.amount_sanctioned))}</span>
        ) : "—",
    },
    {
      key: "expected_payout", header: "Payout",
      render: (l: Loan) =>
        l.expected_payout ? (
          <span className="tabular-nums">
            {show(inr(l.expected_payout))}
            {l.actual_payout ? (
              <span className="block text-xs text-emerald-600">
                {show(inr(l.actual_payout))} received
              </span>
            ) : null}
          </span>
        ) : "—",
    },
    {
      key: "status", header: "Stage", sortable: true,
      render: (l: Loan) => (
        <span className={clsx("badge", STATUS_STYLES[l.status] ?? STATUS_STYLES.enquiry)}>
          {l.status.replace("_", " ")}
        </span>
      ),
    },
  ];

  const extraColumns = [
    { key: "tenure_months", header: "Tenure", render: (l: Loan) => (l.tenure_months ? `${l.tenure_months} mo` : "—") },
    { key: "interest_rate", header: "ROI", render: (l: Loan) => (l.interest_rate ? `${l.interest_rate}%` : "—") },
    { key: "payout_percent", header: "Payout %", render: (l: Loan) => (l.payout_percent ? `${l.payout_percent}%` : "—") },
    { key: "applied_on", header: "Applied", render: (l: Loan) => formatDate(l.applied_on) },
    { key: "disbursed_on", header: "Disbursed", render: (l: Loan) => formatDate(l.disbursed_on) },
    { key: "owner_id", header: "Agent", render: (l: Loan) => l.owner?.first_name ?? "—" },
    { key: "remarks", header: "Remarks", render: (l: Loan) => l.remarks || "—" },
  ];

  const toolbar = (
    <>
      {stats && (
        <span className="hidden items-center gap-3 text-xs text-slate-500 lg:flex dark:text-slate-400">
          <span>{stats.open_cases} open</span>
          <span title="Expected minus received on disbursed cases">
            {show(inr(stats.outstanding_payout))} payout outstanding
          </span>
        </span>
      )}
      <div className="flex overflow-hidden rounded-lg border border-slate-300 dark:border-slate-700">
        {([["list", List], ["board", LayoutGrid]] as const).map(([mode, Icon]) => (
          <button
            key={mode}
            className={clsx(
              "px-2.5 py-1.5 transition-colors",
              view === mode
                ? "bg-primary-600 text-white"
                : "text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            )}
            onClick={() => setView(mode)}
            title={mode === "list" ? "List view" : "Pipeline view"}
          >
            <Icon size={15} />
          </button>
        ))}
      </div>
    </>
  );

  if (view === "board") {
    return (
      <div className="flex h-full min-h-0 flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <Landmark size={20} className="text-primary-600 dark:text-primary-400" />
            Loans
          </h1>
          <div className="flex items-center gap-2">{toolbar}</div>
        </div>
        <LoanBoard />
      </div>
    );
  }

  return (
    <CrudPage<Loan>
      title="Loans"
      singular="Loan"
      endpoint="/loans"
      module="loans"
      filterFields={filterFields}
      schema={schema}
      defaults={defaults}
      fields={fields}
      toForm={(l) => ({
        ...l,
        lender_id: l.lender_id ?? "",
        owner_id: l.owner_id ?? "",
        applied_on: l.applied_on ?? "",
        sanctioned_on: l.sanctioned_on ?? "",
        disbursed_on: l.disbursed_on ?? "",
        rejected_reason: l.rejected_reason ?? "",
        remarks: l.remarks ?? "",
      })}
      searchPlaceholder="Loan type, remarks…"
      columns={columns}
      allColumns={[...columns, ...extraColumns]}
      toolbar={toolbar}
    />
  );
}
