import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { History, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { z } from "zod";

import { CrudPage, FieldDef } from "@/components/CrudPage";
import { CustomerChip } from "@/components/CustomerChip";
import { Modal } from "@/components/Modal";
import { useToast } from "@/context/ToastContext";
import { api, errorMessage } from "@/lib/api";
import { FilterFieldDef } from "@/lib/filters";
import { formatDate } from "@/lib/format";
import { useContactOptions, useUserOptions } from "@/lib/options";
import { useValuePrivacy } from "@/lib/privacy";
import { waTemplates } from "@/lib/whatsapp";
import { numDefault, optNum, optStr, reqStr } from "@/lib/zh";
import type { Master, Policy } from "@/types";

const PRODUCT_LINES = [
  { value: "motor", label: "Motor" },
  { value: "health", label: "Health" },
  { value: "life", label: "Life" },
  { value: "general", label: "General" },
];

const STATUS_STYLES: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  expiring: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  lapsed: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  renewed: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  draft: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  cancelled: "bg-slate-100 text-slate-400 line-through dark:bg-slate-800",
};

const CHANNELS = ["direct", "bank", "online", "referral", "renewal", "agent"].map((v) => ({
  value: v,
  label: v.charAt(0).toUpperCase() + v.slice(1),
}));

const PAYMENT_MODES = ["cash", "cheque", "online", "upi", "card", "netbanking", "auto_debit"].map(
  (v) => ({ value: v, label: v.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase()) })
);

/** Reference lists this tenant maintains — insurers, banks, branches. */
function useMasters(type: string) {
  const { data } = useQuery({
    queryKey: ["masters", type],
    queryFn: async () => (await api.get<Master[]>("/masters", { params: { type } })).data,
    staleTime: 5 * 60_000,
  });
  return (data ?? []).map((m) => ({ value: m.id, label: m.name }));
}

const schema = z.object({
  policy_number: reqStr("Policy number is required"),
  product_line: reqStr("Choose a product line"),
  plan_name: optStr,
  customer_id: reqStr("Choose a customer"),
  insurer_id: optStr,
  broker_id: optStr,
  bank_id: optStr,
  branch: optStr,
  sourcing_channel: optStr,
  owner_id: optStr,
  issue_date: optStr,
  start_date: optStr,
  expiry_date: optStr,
  premium_net: optNum,
  premium_gst: optNum,
  premium_gross: optNum,
  sum_insured: optNum,
  payment_mode: optStr,
  commission_percent: optNum,
  commission_amount: optNum,
  registration_no: optStr,
  remarks: optStr,
  details: z.record(z.any()).default({}),
});

const defaults = {
  policy_number: "", product_line: "motor", plan_name: "", customer_id: "",
  insurer_id: "", broker_id: "", bank_id: "", branch: "", sourcing_channel: "direct", owner_id: "",
  issue_date: "", start_date: "", expiry_date: "",
  premium_net: "", premium_gst: "", premium_gross: "", sum_insured: "",
  payment_mode: "", commission_percent: "", commission_amount: "",
  registration_no: "", remarks: "", details: {} as Record<string, any>,
};

/** The renewal chain for one policy — what the customer was covered for, year by year. */
function HistoryModal({ policyId, onClose }: { policyId: string | null; onClose: () => void }) {
  const { data } = useQuery({
    queryKey: ["policy-history", policyId],
    queryFn: async () => (await api.get<Policy[]>(`/policies/${policyId}/history`)).data,
    enabled: !!policyId,
  });

  return (
    <Modal open={!!policyId} onClose={onClose} title="Renewal history" wide>
      {!data && <p className="text-slate-400">Loading…</p>}
      {data && (
        <ol className="space-y-2">
          {data.map((policy, index) => (
            <li key={policy.id} className="flex items-center gap-3">
              <span className="w-6 shrink-0 text-center text-xs text-slate-400">{index + 1}</span>
              <span className="card flex-1 px-3 py-2">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{policy.policy_number}</span>
                  <span className={clsx("badge", STATUS_STYLES[policy.status])}>{policy.status}</span>
                  <span className="ml-auto text-sm text-slate-500 dark:text-slate-400">
                    {formatDate(policy.start_date)} → {formatDate(policy.expiry_date)}
                  </span>
                </span>
                <span className="mt-0.5 block text-xs text-slate-400">
                  {policy.insurer?.name ?? "—"} · ₹{Number(policy.premium_gross).toLocaleString("en-IN")}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Modal>
  );
}

/** Renew a policy: only what changes is asked for; the rest carries over. */
function RenewModal({ policy, onClose }: { policy: Policy | null; onClose: () => void }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    policy_number: "", start_date: "", expiry_date: "", premium_gross: "", remarks: "",
  });

  const renew = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/policies/${policy!.id}/renew`, {
          ...form,
          premium_gross: form.premium_gross || null,
          remarks: form.remarks || null,
        })
      ).data,
    onSuccess: () => {
      toast("Policy renewed");
      queryClient.invalidateQueries({ queryKey: ["/policies"] });
      queryClient.invalidateQueries({ queryKey: ["renewals"] });
      onClose();
    },
    onError: (err) => toast(errorMessage(err), "error"),
  });

  return (
    <Modal open={!!policy} onClose={onClose} title={`Renew ${policy?.policy_number ?? ""}`}>
      <div className="space-y-4">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          This creates a new policy linked to the old one. Everything you do not change —
          insurer, customer, vehicle details — carries over, and the expiring policy is kept
          as history rather than overwritten.
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="label">New policy number</label>
            <input
              className="input"
              value={form.policy_number}
              onChange={(e) => setForm({ ...form, policy_number: e.target.value })}
              autoFocus
            />
          </div>
          <div>
            <label className="label">New start date</label>
            <input
              className="input" type="date" value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
          </div>
          <div>
            <label className="label">New expiry date</label>
            <input
              className="input" type="date" value={form.expiry_date}
              onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Renewal premium (gross)</label>
            <input
              className="input" type="number" step="0.01" value={form.premium_gross}
              placeholder={String(policy?.premium_gross ?? "")}
              onChange={(e) => setForm({ ...form, premium_gross: e.target.value })}
            />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={
              renew.isPending || !form.policy_number.trim() || !form.start_date || !form.expiry_date
            }
            onClick={() => renew.mutate()}
          >
            {renew.isPending ? "Renewing…" : "Create renewal"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export default function Policies() {
  const insurers = useMasters("insurer");
  const brokers = useMasters("broker");
  const banks = useMasters("bank");
  const customers = useContactOptions();
  const users = useUserOptions();
  const { show } = useValuePrivacy();
  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [renewing, setRenewing] = useState<Policy | null>(null);

  const filterFields: FilterFieldDef[] = [
    { key: "product_line", label: "Product line", type: "select", options: PRODUCT_LINES },
    {
      key: "status", label: "Status", type: "select",
      options: ["active", "expiring", "lapsed", "renewed", "draft", "cancelled"].map((v) => ({ value: v, label: v })),
    },
    { key: "insurer_id", label: "Insurer", type: "select", options: insurers },
    { key: "broker_id", label: "Insurance company", type: "select", options: brokers },
    { key: "bank_id", label: "Bank", type: "select", options: banks },
    { key: "sourcing_channel", label: "Sourced via", type: "select", options: CHANNELS },
    { key: "owner_id", label: "Agent", type: "select", options: users },
    { key: "expiry_date", label: "Expiry date", type: "date" },
    { key: "issue_date", label: "Issue date", type: "date" },
    { key: "premium_gross", label: "Premium", type: "number" },
    { key: "registration_no", label: "Registration no.", type: "text" },
  ];

  const fields: FieldDef[] = [
    { name: "policy_number", label: "Policy number", section: "Policy" },
    { name: "product_line", label: "Product line", type: "select", options: PRODUCT_LINES, section: "Policy" },
    { name: "customer_id", label: "Customer", type: "select", options: customers, section: "Policy" },
    { name: "insurer_id", label: "Insurer", type: "select", options: insurers, section: "Policy" },
    {
      name: "broker_id", label: "Insurance company", type: "select", options: brokers,
      section: "Policy",
      placeholder: "Placed through…",
    },
    { name: "plan_name", label: "Plan", section: "Policy" },
    { name: "owner_id", label: "Agent", type: "select", options: users, section: "Policy" },

    { name: "issue_date", label: "Issue date", type: "date", section: "Dates" },
    { name: "start_date", label: "Risk start date", type: "date", section: "Dates" },
    { name: "expiry_date", label: "Expiry date", type: "date", section: "Dates" },

    { name: "premium_net", label: "Premium (net)", type: "number", step: "0.01", section: "Premium" },
    { name: "premium_gst", label: "GST", type: "number", step: "0.01", section: "Premium" },
    {
      name: "premium_gross", label: "Premium (gross)", type: "number", step: "0.01", section: "Premium",
      after: () => (
        <p className="text-xs text-slate-400">
          Leave any one of these blank and it is worked out from the other two.
        </p>
      ),
    },
    { name: "sum_insured", label: "Sum insured / IDV", type: "number", step: "0.01", section: "Premium" },
    { name: "payment_mode", label: "Payment mode", type: "select", options: PAYMENT_MODES, section: "Premium" },
    { name: "commission_percent", label: "Commission %", type: "number", step: "0.01", section: "Premium" },

    { name: "bank_id", label: "Sourced through bank", type: "select", options: banks, section: "Sourcing" },
    { name: "sourcing_channel", label: "Channel", type: "select", options: CHANNELS, section: "Sourcing" },
    { name: "branch", label: "Branch", section: "Sourcing" },
    { name: "registration_no", label: "Vehicle registration no.", section: "Sourcing", placeholder: "TN01AB1234" },

    { name: "remarks", label: "Remarks", type: "textarea", colSpan: 2, section: "Sourcing" },
  ];

  const columns = [
    {
      key: "policy_number", header: "Policy", sortable: true,
      render: (p: Policy) => (
        <span>
          <span className="block font-medium">{p.policy_number}</span>
          <span className="block text-xs capitalize text-slate-400">
            {p.product_line}
            {p.registration_no ? ` · ${p.registration_no}` : ""}
          </span>
        </span>
      ),
    },
    {
      key: "customer_id", header: "Customer",
      render: (p: Policy) =>
        p.customer ? (
          <CustomerChip
            person={p.customer}
            compact
            message={waTemplates.renewal(p.customer.full_name, p.policy_number)}
          />
        ) : "—",
    },
    { key: "insurer_id", header: "Insurer", render: (p: Policy) => p.insurer?.name ?? "—" },
    { key: "broker_id", header: "Insurance company", render: (p: Policy) => p.broker?.name ?? "—" },
    {
      key: "expiry_date", header: "Expiry", sortable: true,
      render: (p: Policy) => (
        <span>
          <span className="block">{formatDate(p.expiry_date)}</span>
          {typeof p.days_to_expiry === "number" && p.days_to_expiry >= 0 && p.days_to_expiry <= 60 && (
            <span className="block text-xs font-medium text-amber-600 dark:text-amber-400">
              in {p.days_to_expiry} days
            </span>
          )}
        </span>
      ),
    },
    {
      key: "premium_gross", header: "Premium", sortable: true,
      render: (p: Policy) => (
        <span className="tabular-nums">
          {show(`₹${Number(p.premium_gross).toLocaleString("en-IN")}`)}
        </span>
      ),
    },
    {
      key: "status", header: "Status", sortable: true,
      render: (p: Policy) => (
        <span className={clsx("badge", STATUS_STYLES[p.status] ?? STATUS_STYLES.draft)}>
          {p.status}
        </span>
      ),
    },
  ];

  const extraColumns = [
    { key: "plan_name", header: "Plan", render: (p: Policy) => p.plan_name || "—" },
    { key: "bank_id", header: "Bank", render: (p: Policy) => p.bank?.name ?? "—" },
    { key: "sourcing_channel", header: "Channel", render: (p: Policy) => p.sourcing_channel ?? "—" },
    { key: "branch", header: "Branch", render: (p: Policy) => p.branch || "—" },
    { key: "start_date", header: "Start date", render: (p: Policy) => formatDate(p.start_date) },
    { key: "issue_date", header: "Issue date", render: (p: Policy) => formatDate(p.issue_date) },
    {
      key: "sum_insured", header: "Sum insured",
      render: (p: Policy) => show(p.sum_insured ? `₹${Number(p.sum_insured).toLocaleString("en-IN")}` : "—"),
    },
    {
      key: "commission_amount", header: "Commission",
      render: (p: Policy) =>
        show(p.commission_amount ? `₹${Number(p.commission_amount).toLocaleString("en-IN")}` : "—"),
    },
    { key: "owner_id", header: "Agent", render: (p: Policy) => p.owner?.first_name ?? "—" },
  ];

  return (
    <>
      <CrudPage<Policy>
        title="Policies"
        singular="Policy"
        endpoint="/policies"
        module="policies"
        filterFields={filterFields}
        schema={schema}
        defaults={defaults}
        fields={fields}
        toForm={(p) => ({
          ...p,
          insurer_id: p.insurer_id ?? "",
          broker_id: p.broker_id ?? "",
          bank_id: p.bank_id ?? "",
          owner_id: p.owner_id ?? "",
          plan_name: p.plan_name ?? "",
          branch: p.branch ?? "",
          sourcing_channel: p.sourcing_channel ?? "",
          payment_mode: p.payment_mode ?? "",
          registration_no: p.registration_no ?? "",
          remarks: p.remarks ?? "",
          issue_date: p.issue_date ?? "",
          start_date: p.start_date ?? "",
          expiry_date: p.expiry_date ?? "",
        })}
        searchPlaceholder="Policy number, registration…"
        columns={columns}
        allColumns={[...columns, ...extraColumns]}
        rowActions={(policy) => (
          <>
            <button
              className="btn-ghost !p-1.5"
              title="Renewal history"
              onClick={() => setHistoryFor(policy.id)}
            >
              <History size={14} />
            </button>
            {!policy.renewed_to_id && policy.status !== "cancelled" && (
              <button
                className="btn-ghost !p-1.5 text-primary-600"
                title="Renew this policy"
                onClick={() => setRenewing(policy)}
              >
                <RefreshCw size={14} />
              </button>
            )}
          </>
        )}
        toolbar={
          <span className="flex items-center gap-1.5 text-xs text-slate-400">
            <ShieldCheck size={14} /> Status follows the expiry date
          </span>
        }
      />
      <HistoryModal policyId={historyFor} onClose={() => setHistoryFor(null)} />
      <RenewModal policy={renewing} onClose={() => setRenewing(null)} />
    </>
  );
}
