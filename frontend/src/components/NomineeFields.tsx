import clsx from "clsx";
import { AlertTriangle, Plus, Trash2, UserPlus } from "lucide-react";
import { Controller } from "react-hook-form";

import { Select } from "@/components/Select";

export interface NomineeDraft {
  name: string;
  relation?: string | null;
  age?: number | string | null;
  share_percent?: number | string | null;
  appointee_name?: string | null;
  appointee_relation?: string | null;
}

/** The relations an insurer's proposal form actually offers. */
const RELATIONS = [
  "Spouse", "Son", "Daughter", "Father", "Mother", "Brother", "Sister",
  "Grandson", "Granddaughter", "Other",
].map((v) => ({ value: v, label: v }));

const blank = (share: number): NomineeDraft => ({
  name: "", relation: "", age: "", share_percent: share,
  appointee_name: "", appointee_relation: "",
});

export const isMinor = (age: number | string | null | undefined) =>
  age !== "" && age !== null && age !== undefined && Number(age) < 18;

export const shareTotal = (rows: NomineeDraft[]) =>
  rows.reduce((sum, n) => sum + Number(n.share_percent || 0), 0);

/**
 * Who receives the benefit if the customer dies.
 *
 * The API has accepted nominees since the customer module was built and nothing has
 * ever asked for them, so every customer in the system has none — an agent filling
 * in a proposal had to get the name, age and relation from somewhere else.
 *
 * Two rules are the insurer's, not ours, and both are enforced server-side: shares
 * across a customer's nominees must total 100, and a nominee under 18 needs an
 * appointee to receive on their behalf. They are surfaced here as they are typed
 * rather than as a refusal on save, because being told which of four rows is wrong
 * is worth more than being told the set is.
 */
export function NomineeFields({ control, name }: { control: any; name: string }) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => {
        const rows: NomineeDraft[] = field.value ?? [];
        const total = shareTotal(rows);

        const set = (index: number, patch: Partial<NomineeDraft>) =>
          field.onChange(rows.map((n, i) => (i === index ? { ...n, ...patch } : n)));

        /**
         * A new row takes whatever share is unallocated; if there is none, the
         * shares are split evenly instead. Appending a 0% nominee would look
         * reasonable, total 100 with the others, and then be refused by the API,
         * which requires every share to be at least 1.
         */
        const add = () => {
          const spare = 100 - total;
          if (spare > 0) {
            field.onChange([...rows, blank(spare)]);
            return;
          }
          const next = [...rows, blank(0)];
          const each = Math.floor(100 / next.length);
          field.onChange(
            next.map((n, i) => ({
              ...n,
              share_percent: i === 0 ? 100 - each * (next.length - 1) : each,
            }))
          );
        };

        const remove = (index: number) => {
          const next = rows.filter((_, i) => i !== index);
          // One nominee left holding a part share is always a mistake, never a choice.
          field.onChange(next.length === 1 ? [{ ...next[0], share_percent: 100 }] : next);
        };

        /** Split evenly, giving any remainder to the first — 3 rows become 34/33/33. */
        const splitEvenly = () => {
          if (!rows.length) return;
          const each = Math.floor(100 / rows.length);
          field.onChange(
            rows.map((n, i) => ({
              ...n,
              share_percent: i === 0 ? 100 - each * (rows.length - 1) : each,
            }))
          );
        };

        return (
          <div className="space-y-2">
            {rows.length === 0 && (
              <button
                type="button"
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 px-3 py-4 text-sm text-slate-500 transition-colors hover:border-primary-400 hover:text-primary-600 dark:border-slate-700 dark:text-slate-400"
                onClick={add}
              >
                <UserPlus size={15} /> Add a nominee
              </button>
            )}

            {rows.map((nominee, index) => (
              <div
                key={index}
                className="rounded-lg border border-slate-200 p-2.5 dark:border-slate-700"
              >
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-[minmax(0,2fr)_minmax(0,1.4fr)_5rem_6rem_auto]">
                  <div>
                    <label className="label !mb-0.5 !text-[10px]">Name</label>
                    <input
                      className="input !py-1.5"
                      value={nominee.name ?? ""}
                      placeholder="Full name"
                      onChange={(e) => set(index, { name: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="label !mb-0.5 !text-[10px]">Relation</label>
                    <Select
                      options={RELATIONS}
                      value={nominee.relation ?? ""}
                      onChange={(v) => set(index, { relation: v })}
                    />
                  </div>
                  <div>
                    <label className="label !mb-0.5 !text-[10px]">Age</label>
                    <input
                      type="number"
                      min={0}
                      max={120}
                      className="input !py-1.5"
                      value={nominee.age ?? ""}
                      onChange={(e) => set(index, { age: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="label !mb-0.5 !text-[10px]">Share %</label>
                    <input
                      type="number"
                      min={1}
                      max={100}
                      className="input !py-1.5"
                      value={nominee.share_percent ?? ""}
                      onChange={(e) => set(index, { share_percent: e.target.value })}
                    />
                  </div>
                  <div className="flex items-end justify-end">
                    <button
                      type="button"
                      className="btn-ghost !p-2 text-slate-400 hover:text-red-500"
                      title="Remove this nominee"
                      onClick={() => remove(index)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {/* Only asked for when it is actually required, so the form does not
                    carry two dead boxes for every adult nominee. */}
                {isMinor(nominee.age) && (
                  <div className="mt-2 rounded-lg bg-amber-50 p-2 dark:bg-amber-950/30">
                    <p className="mb-1.5 flex items-center gap-1.5 text-xs text-amber-800 dark:text-amber-200">
                      <AlertTriangle size={12} className="shrink-0" />
                      Under 18 — an insurer needs an appointee to receive on their behalf.
                    </p>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      <input
                        className="input !py-1.5"
                        placeholder="Appointee name"
                        value={nominee.appointee_name ?? ""}
                        onChange={(e) => set(index, { appointee_name: e.target.value })}
                      />
                      <Select
                        options={RELATIONS}
                        value={nominee.appointee_relation ?? ""}
                        onChange={(v) => set(index, { appointee_relation: v })}
                      />
                    </div>
                  </div>
                )}
              </div>
            ))}

            {rows.length > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button type="button" className="btn-secondary !py-1.5 text-xs" onClick={add}>
                  <Plus size={13} /> Add another
                </button>
                <span className="flex items-center gap-2 text-xs">
                  {rows.length > 1 && total !== 100 && (
                    <button
                      type="button"
                      className="btn-ghost !px-2 !py-1 text-xs text-primary-600 dark:text-primary-400"
                      onClick={splitEvenly}
                    >
                      Split evenly
                    </button>
                  )}
                  <span
                    className={clsx(
                      "font-medium tabular-nums",
                      total === 100
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-amber-600 dark:text-amber-400"
                    )}
                  >
                    Shares total {total}%
                    {total !== 100 && " — must be 100"}
                  </span>
                </span>
              </div>
            )}
          </div>
        );
      }}
    />
  );
}
