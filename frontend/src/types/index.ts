export interface Role {
  id: string;
  name: string;
  description?: string | null;
  permissions: string[];
  is_system: boolean;
}

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone?: string | null;
  avatar_url?: string | null;
  is_active: boolean;
  theme: string;
  last_login_at?: string | null;
  created_at: string;
  role: Role;
}

export interface UserBrief {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  avatar_url?: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Company {
  id: string;
  name: string;
  industry?: string | null;
  website?: string | null;
  gst_number?: string | null;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  postal_code?: string | null;
  notes?: string | null;
  tags: string[];
  owner_id?: string | null;
  owner?: UserBrief | null;
  created_at: string;
}

export interface Contact {
  id: string;
  first_name: string;
  last_name: string;
  position?: string | null;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  emails: string[];
  phones: string[];
  social_links: Record<string, string>;
  notes?: string | null;
  tags: string[];
  owner?: UserBrief | null;
  created_at: string;
}

export interface LeadSource {
  id: string;
  name: string;
}

export interface Lead {
  id: string;
  title: string;
  contact_name?: string | null;
  email?: string | null;
  phone?: string | null;
  company_name?: string | null;
  source_id?: string | null;
  source?: LeadSource | null;
  status: string;
  score: number;
  assigned_to_id?: string | null;
  assigned_to?: UserBrief | null;
  notes?: string | null;
  follow_up_at?: string | null;
  converted_deal_id?: string | null;
  created_at: string;
}

export interface DealStage {
  id: string;
  name: string;
  order: number;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
  deal_count?: number;
}

export interface Deal {
  id: string;
  title: string;
  value: number;
  currency: string;
  probability: number;
  expected_close_date?: string | null;
  stage_id: string;
  stage?: DealStage | null;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  contact_id?: string | null;
  contact?: { id: string; first_name: string; last_name: string } | null;
  owner_id?: string | null;
  owner?: UserBrief | null;
  competitors?: string | null;
  notes?: string | null;
  status: string;
  created_at: string;
}

export interface PipelineColumn {
  stage: DealStage;
  deals: Deal[];
  total_value: number;
}

export interface Task {
  id: string;
  title: string;
  description?: string | null;
  priority: string;
  status: string;
  due_date?: string | null;
  assigned_to_id?: string | null;
  assigned_to?: UserBrief | null;
  created_by?: UserBrief | null;
  entity_type?: string | null;
  entity_id?: string | null;
  created_at: string;
}

export interface Meeting {
  id: string;
  title: string;
  agenda?: string | null;
  starts_at: string;
  ends_at?: string | null;
  location?: string | null;
  participant_ids: string[];
  external_participants: string[];
  notes?: string | null;
  organizer?: UserBrief | null;
  created_at: string;
}

export interface CalendarItem {
  id: string;
  kind: string;
  title: string;
  type: string;
  starts_at: string;
  ends_at?: string | null;
  location?: string | null;
}

export interface Product {
  id: string;
  name: string;
  sku?: string | null;
  description?: string | null;
  category?: string | null;
  unit_price: number;
  currency: string;
  tax_rate: number;
  stock_qty?: number | null;
  is_active: boolean;
  created_at: string;
}

export interface LineItem {
  id?: string;
  product_id?: string | null;
  name: string;
  description?: string | null;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  line_total?: number;
}

export interface Quotation {
  id: string;
  number: string;
  status: string;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  contact_id?: string | null;
  contact?: { id: string; first_name: string; last_name: string } | null;
  deal_id?: string | null;
  issue_date?: string | null;
  valid_until?: string | null;
  currency: string;
  subtotal: number;
  tax_total: number;
  discount: number;
  total: number;
  notes?: string | null;
  terms?: string | null;
  items: LineItem[];
  created_at: string;
}

export interface Invoice {
  id: string;
  number: string;
  quotation_id?: string | null;
  status: string;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  contact_id?: string | null;
  issue_date?: string | null;
  due_date?: string | null;
  currency: string;
  subtotal: number;
  tax_total: number;
  discount: number;
  total: number;
  amount_paid: number;
  notes?: string | null;
  items: LineItem[];
  created_at: string;
}

export interface ProjectTask {
  id: string;
  title: string;
  is_milestone: boolean;
  status: string;
  due_date?: string | null;
  assigned_to?: UserBrief | null;
  position: number;
}

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  status: string;
  start_date?: string | null;
  end_date?: string | null;
  budget?: number | null;
  owner?: UserBrief | null;
  team_ids: string[];
  tasks: ProjectTask[];
  created_at: string;
}

export interface Ticket {
  id: string;
  number: string;
  subject: string;
  description?: string | null;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  contact_id?: string | null;
  priority: string;
  status: string;
  assigned_to_id?: string | null;
  assigned_to?: UserBrief | null;
  resolution?: string | null;
  created_at: string;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body?: string | null;
  link?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface AppSetting {
  key: string;
  value: Record<string, any>;
}

export interface TemplateVariable {
  key: string;
  label: string;
  sample: string;
}

export interface EmailTemplate {
  id: string;
  name: string;
  subject: string;
  body_html: string;
  description?: string | null;
  updated_at: string;
  variables?: TemplateVariable[];
}
