export type FilterType = "text" | "select" | "date" | "number";

export interface FilterFieldDef {
  key: string;
  label: string;
  type: FilterType;
  options?: { value: string; label: string }[]; // for select
}

export interface ActiveFilter {
  key: string;
  type: FilterType;
  value?: any; // text: string; select: string[]; number: number
  op?: "eq" | "gte" | "lte"; // number
  from?: string; // date
  to?: string; // date
}

/** Is this filter meaningfully set (worth sending / counting as active)? */
export function isFilterActive(f: ActiveFilter | undefined): boolean {
  if (!f) return false;
  switch (f.type) {
    case "text":
      return !!(f.value && String(f.value).trim());
    case "select":
      return Array.isArray(f.value) && f.value.length > 0;
    case "number":
      return f.value !== undefined && f.value !== null && f.value !== "";
    case "date":
      return !!(f.from || f.to);
    default:
      return false;
  }
}

/** Serialize the active filters to the JSON string the API expects, or undefined. */
export function serializeFilters(filters: ActiveFilter[]): string | undefined {
  const active = filters.filter(isFilterActive);
  return active.length ? JSON.stringify(active) : undefined;
}

export function countActive(filters: ActiveFilter[]): number {
  return filters.filter(isFilterActive).length;
}
