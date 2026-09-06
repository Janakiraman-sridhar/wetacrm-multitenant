import { useQuery } from "@tanstack/react-query";

import type { SelectOption } from "@/components/CrudPage";
import { api } from "@/lib/api";
import type { Company, Contact, DealStage, LeadSource, Page, Product, Tag, UserBrief } from "@/types";

/** Configured product/service tags (Settings → Tags), as multi-select options keyed by name. */
export function useTagOptions(): SelectOption[] {
  const { data } = useQuery({
    queryKey: ["options", "tags"],
    queryFn: async () => (await api.get<Tag[]>("/settings/tags")).data,
    staleTime: 60_000,
  });
  return (data ?? []).map((t) => ({ value: t.name, label: t.name }));
}

export function useUserOptions(): SelectOption[] {
  const { data } = useQuery({
    queryKey: ["options", "users"],
    queryFn: async () => (await api.get<UserBrief[]>("/users/all")).data,
    staleTime: 60_000,
  });
  return (data ?? []).map((u) => ({ value: u.id, label: `${u.first_name} ${u.last_name}`.trim() || u.email }));
}

export function useCompanyOptions(): SelectOption[] {
  const { data } = useQuery({
    queryKey: ["options", "companies"],
    queryFn: async () => (await api.get<Page<Company>>("/companies", { params: { page_size: 200, sort: "name" } })).data,
    staleTime: 30_000,
  });
  return (data?.items ?? []).map((c) => ({ value: c.id, label: c.name }));
}

export function useContactOptions(): SelectOption[] {
  const { data } = useQuery({
    queryKey: ["options", "contacts"],
    queryFn: async () => (await api.get<Page<Contact>>("/contacts", { params: { page_size: 200, sort: "first_name" } })).data,
    staleTime: 30_000,
  });
  return (data?.items ?? []).map((c) => ({ value: c.id, label: `${c.first_name} ${c.last_name}`.trim() }));
}

export function useStageOptions(): SelectOption[] {
  const { data } = useQuery({
    queryKey: ["options", "stages"],
    queryFn: async () => (await api.get<DealStage[]>("/deals/stages")).data,
    staleTime: 300_000,
  });
  return (data ?? []).map((s) => ({ value: s.id, label: s.name }));
}

export function useSourceOptions(): SelectOption[] {
  const { data } = useQuery({
    queryKey: ["options", "sources"],
    queryFn: async () => (await api.get<LeadSource[]>("/leads/sources")).data,
    staleTime: 300_000,
  });
  return (data ?? []).map((s) => ({ value: s.id, label: s.name }));
}

export function useProducts(): Product[] {
  const { data } = useQuery({
    queryKey: ["options", "products"],
    queryFn: async () =>
      (await api.get<Page<Product>>("/products", { params: { page_size: 200, active_only: true, sort: "name" } })).data,
    staleTime: 30_000,
  });
  return data?.items ?? [];
}
