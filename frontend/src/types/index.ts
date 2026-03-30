export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: "admin" | "operator" | "viewer";
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

export type CampaignStatus =
  | "draft"
  | "scheduled"
  | "running"
  | "paused"
  | "completed"
  | "cancelled";

export interface Campaign {
  id: string;
  name: string;
  description: string;
  status: CampaignStatus;
  template_id: string;
  landing_page_id: string | null;
  address_book_id: string;
  smtp_profile_id: string;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  stats: CampaignStats;
  send_rate?: number;
  training_url?: string;
  training_redirect_delay?: number;
  send_window_start?: string;
  send_window_end?: string;
  throttle_rate?: number;
}

export interface CampaignStats {
  total_recipients: number;
  emails_sent: number;
  emails_opened: number;
  links_clicked: number;
  credentials_submitted: number;
  reported: number;
  errors: number;
}

export interface Contact {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  position: string;
  department: string;
  address_book_id: string;
  custom_fields: Record<string, string>;
  created_at: string;
}

export interface AddressBook {
  id: string;
  name: string;
  description: string;
  contact_count: number;
  source_file: string;
  status: "ready" | "processing" | "error";
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface EmailTemplate {
  id: string;
  name: string;
  subject: string;
  body_html: string;
  body_text: string;
  envelope_sender: string;
  category: string;
  difficulty?: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PretextTemplate {
  id: string;
  name: string;
  subject: string;
  body_html: string;
  body_text: string;
  category: "IT" | "HR" | "Finance" | "Executive" | "Vendor";
  difficulty: number;
  description: string;
}

export interface LandingPage {
  id: string;
  name: string;
  description: string;
  html_content: string;
  capture_credentials: boolean;
  capture_passwords: boolean;
  redirect_url: string;
  category?: string;
  thumbnail_url?: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface BuiltinLandingPage {
  id: string;
  name: string;
  category: string;
  thumbnail_url: string;
  description: string;
}

export interface SmtpProfile {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  use_tls: boolean;
  from_address: string;
  smtp_type?: string;
  status?: "active" | "inactive" | "error";
  created_by: string;
  created_at: string;
}

export interface TrackingEvent {
  id: string;
  campaign_id: string;
  contact_id: string;
  contact_name?: string;
  contact_email?: string;
  event_type: "sent" | "delivered" | "opened" | "clicked" | "submitted" | "reported" | "error";
  ip_address: string | null;
  user_agent: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogEntry {
  id: string;
  user_id: string;
  username: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  before_state?: Record<string, unknown>;
  after_state?: Record<string, unknown>;
  ip_address: string;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApiError {
  status: number;
  message: string;
  detail: string | null;
}

// -- Report and metrics types --

export interface CampaignMetrics {
  campaign_id: string;
  campaign_name: string;
  sent: number;
  opened: number;
  clicked: number;
  submitted: number;
  reported: number;
  open_rate: number;
  click_rate: number;
  submit_rate: number;
  report_rate: number;
  time_to_click_distribution: { bucket: string; count: number }[];
  click_rate_by_hour: { hour: number; rate: number }[];
  top_clicked_links: { url: string; clicks: number }[];
}

export interface DepartmentMetrics {
  department: string;
  total_contacts: number;
  emails_sent: number;
  opened: number;
  clicked: number;
  submitted: number;
  open_rate: number;
  click_rate: number;
  submit_rate: number;
  risk_score: number;
}

export interface TrendData {
  campaign_id: string;
  campaign_name: string;
  date: string;
  click_rate: number;
  open_rate: number;
  submit_rate: number;
}

export interface OrgRiskScore {
  score: number;
  level: "low" | "medium" | "high" | "critical";
  trend: number;
  top_risk_departments: { department: string; score: number }[];
}

export interface ExecutiveSummary {
  org_risk: OrgRiskScore;
  total_campaigns: number;
  total_emails_sent: number;
  avg_click_rate: number;
  avg_open_rate: number;
  avg_submit_rate: number;
  department_metrics: DepartmentMetrics[];
  trend_data: TrendData[];
}

// -- Live monitoring types --

export interface LiveCampaignStats {
  campaign_id: string;
  campaign_name: string;
  status: CampaignStatus;
  progress: number;
  send_rate: number;
  started_at: string;
  eta: string | null;
  stats: CampaignStats;
}

export interface EventFeedItem {
  id: string;
  event_type: string;
  description: string;
  campaign_name: string;
  contact_name?: string;
  timestamp: string;
}

export interface SendRatePoint {
  timestamp: string;
  rate: number;
}

// -- API Key type --

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  raw_key?: string;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  is_active: boolean;
}

// -- Report type enum --

export enum ReportType {
  EXECUTIVE_SUMMARY = "executive_summary",
  DEPARTMENT_BREAKDOWN = "department_breakdown",
  TREND_ANALYSIS = "trend_analysis",
  COMPLIANCE_PACKAGE = "compliance_package",
}

// -- Column mapping types --

export interface DetectedColumn {
  source_column: string;
  sample_values: string[];
  suggested_mapping: string | null;
}

export interface ColumnMapping {
  source_column: string;
  target_field: string;
}

// -- Dashboard stats --

export interface DashboardStats {
  active_campaigns: number;
  active_campaigns_change: number;
  total_contacts: number;
  total_contacts_change: number;
  emails_sent_month: number;
  emails_sent_change: number;
  org_risk: OrgRiskScore;
}

// -- Recipient status in campaign detail --

export interface CampaignRecipient {
  id: string;
  contact_id: string;
  first_name: string;
  last_name: string;
  email: string;
  department: string;
  status: "pending" | "sent" | "opened" | "clicked" | "submitted" | "reported";
  events: TrackingEvent[];
}

// -- General settings --

export interface GeneralSettings {
  app_name: string;
  default_throttle_rate: number;
  upload_directory: string;
  log_level: "debug" | "info" | "warning" | "error";
}
