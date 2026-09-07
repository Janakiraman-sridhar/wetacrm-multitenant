import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { FieldDef, SelectOption } from "@/components/CrudPage";
import type { Column } from "@/components/DataTable";
import { api } from "@/lib/api";
import type { FilterFieldDef } from "@/lib/filters";

/** One field in a module's schema, as this tenant has configured it. */
export interface SchemaField {
  key: string;
  label: string;
  type: string;
  required: boolean;
  options: SelectOption[];
  section: string | null;
  order: number;
  help_text: string | null;
  placeholder: string | null;
  default_value?: string | null;
  is_custom: boolean;
  locked: boolean;
  is_active: boolean;
  show_in_table: boolean;
  filterable: boolean;
  is_pii: boolean;
  id?: string;
}

export interface ModuleSchema {
  module: string;
  fields: SchemaField[];
}

/**
 * A module's field schema for the current tenant.
 *
 * Pages keep their own hand-built field and column definitions as the base — those
 * carry render details the server cannot know, like which hook supplies a select's
 * options. This adds what only the tenant knows: relabelled base fields, hidden
 * ones, and fields they invented.
 */
export function useModuleSchema(module: string) {
  return useQuery({
    queryKey: ["schema", module],
    queryFn: async () => (await api.get<ModuleSchema>(`/schema/${module}`)).data,
    staleTime: 5 * 60_000,
    // Modules without custom-field support answer 404; that is not an error here.
    retry: false,
  });
}

const TEXTUAL = new Set(["text", "textarea", "email", "phone", "url"]);

/** Map a schema field type onto the form control CrudPage renders. */
function controlFor(type: string): FieldDef["type"] {
  if (type === "textarea") return "textarea";
  if (type === "select") return "select";
  if (type === "multiselect") return "multiselect";
  if (type === "checkbox") return "checkbox";
  if (type === "date") return "date";
  if (type === "datetime") return "datetime-local";
  if (type === "email") return "email";
  if (type === "number" || type === "decimal" || type === "currency") return "number";
  return "text";
}

export interface SchemaOverlay {
  /** Custom fields to append to the form, already in CrudPage's shape. */
  customFields: FieldDef[];
  /** Custom fields the tenant wants in the table. */
  customColumns: Column<any>[];
  /** Custom fields the tenant marked filterable. */
  customFilters: FilterFieldDef[];
  /** New labels for base fields, keyed by field name. */
  labels: Record<string, string>;
  /** Base fields this tenant switched off. */
  hidden: Set<string>;
  /** Empty values for the custom fields, to seed the form. */
  defaults: Record<string, any>;
  ready: boolean;
}

const EMPTY: SchemaOverlay = {
  customFields: [],
  customColumns: [],
  customFilters: [],
  labels: {},
  hidden: new Set(),
  defaults: {},
  ready: false,
};

/** Turn a module's schema into the pieces CrudPage needs. */
export function useSchemaOverlay(module: string): SchemaOverlay {
  const { data } = useModuleSchema(module);

  return useMemo(() => {
    if (!data?.fields) return EMPTY;

    const labels: Record<string, string> = {};
    const hidden = new Set<string>();
    const customFields: FieldDef[] = [];
    const customColumns: Column<any>[] = [];
    const customFilters: FilterFieldDef[] = [];
    const defaults: Record<string, any> = {};

    for (const field of data.fields) {
      if (!field.is_custom) {
        labels[field.key] = field.label;
        if (!field.is_active) hidden.add(field.key);
        continue;
      }
      if (!field.is_active) continue;

      const control = controlFor(field.type);
      customFields.push({
        name: `custom.${field.key}`,
        label: field.label,
        type: control,
        options: field.options,
        placeholder: field.placeholder ?? undefined,
        section: field.section ?? "Additional details",
        colSpan: field.type === "textarea" ? 2 : 1,
        step: field.type === "decimal" || field.type === "currency" ? "0.01" : undefined,
      });

      defaults[field.key] =
        control === "multiselect" ? [] : control === "checkbox" ? false : field.default_value ?? "";

      if (field.show_in_table) {
        customColumns.push({
          key: `custom.${field.key}`,
          header: field.label,
          render: (row: any) => {
            const value = row?.custom?.[field.key];
            if (value === null || value === undefined || value === "") return "—";
            if (Array.isArray(value)) return value.join(", ");
            if (typeof value === "boolean") return value ? "Yes" : "No";
            return String(value);
          },
        });
      }

      if (field.filterable) {
        customFilters.push({
          key: `custom.${field.key}`,
          label: field.label,
          type: TEXTUAL.has(field.type)
            ? "text"
            : field.type === "select" || field.type === "multiselect"
              ? "select"
              : field.type === "date" || field.type === "datetime"
                ? "date"
                : "number",
          options: field.options,
        } as FilterFieldDef);
      }
    }

    return { customFields, customColumns, customFilters, labels, hidden, defaults, ready: true };
  }, [data]);
}
