export type UserRole = 'user' | 'developer' | 'security_analyst' | 'admin' | 'super_admin';
export type UserStatus = 'active' | 'disabled';

export interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  created_at: string;
}

export type AssetType = 'server' | 'workstation' | 'cloud_resource' | 'database' | 'network_device';
export type BusinessCriticality = 'low' | 'medium' | 'high' | 'critical';
export type PatchStatus = 'unknown' | 'not_started' | 'in_progress' | 'patched' | 'accepted_risk' | 'not_applicable';
export type ExploitEvidence = 'none' | 'unconfirmed' | 'public_poc' | 'active_exploitation' | 'internal_confirmation';

export interface Asset {
  id: string;
  name: string;
  type: AssetType;
  hostname: string;
  ip_address: string;
  operating_system: string;
  owner: string;
  department: string;
  business_criticality: BusinessCriticality;
  internet_exposed: boolean;
  description: string;
  created_at: string;
  updated_at: string;
  linked_cves?: string[];
  patch_status?: PatchStatus;
  exploit_evidence?: ExploitEvidence;
}

export interface Vulnerability {
  id: string; /* CVE ID */
  title: string;
  description: string;
  cvss: number;
  severity: 'low' | 'medium' | 'high' | 'critical';
  published_date: string;
  updated_date: string;
  references: string[];
  affected_products: string[];
  remediation?: string;
}

export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical';
export type AlertStatus = 'new' | 'acknowledged' | 'investigating' | 'resolved' | 'false_positive';

export interface Alert {
  id: string;
  title: string;
  description: string;
  severity: AlertSeverity;
  source: string;
  status: AlertStatus;
  asset_id: string;
  cve_id?: string;
  created_at: string;
  updated_at: string;
}

export type IncidentSeverity = 'low' | 'medium' | 'high' | 'critical';
export type IncidentStatus = 'open' | 'triaged' | 'in_progress' | 'contained' | 'eradicated' | 'recovered' | 'closed';

export interface Incident {
  id: string;
  title: string;
  description: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  assignee_id?: string; /* User ID */
  source_alert_id?: string;
  asset_id: string;
  cve_id?: string;
  created_at: string;
  updated_at: string;
  closed_at?: string;
}

export interface PlaybookStep {
  id: string;
  label: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  completed_at?: string;
  completed_by?: string;
}

export interface Playbook {
  id: string;
  name: string;
  description: string;
  category: 'phishing' | 'malware' | 'ransomware' | 'cve_exploit' | 'leak';
  steps: PlaybookStep[];
  priority: 'low' | 'medium' | 'high';
  estimated_duration: string;
}

export type IOCType = 'ip' | 'domain' | 'url' | 'sha256' | 'md5';

export interface IOC {
  id: string;
  value: string;
  type: IOCType;
  severity: 'low' | 'medium' | 'high' | 'critical';
  description: string;
  first_seen: string;
  last_seen: string;
  watchlist: boolean;
  related_incidents?: string[];
}

export interface IOCRelation {
  source: string;
  target: string;
  type: string;
}

export interface NewsArticle {
  id: string;
  title: string;
  summary: string;
  ai_summary?: string;
  url: string;
  source: string;
  published_at: string;
  category: string;
  related_cves?: string[];
  bookmarked: boolean;
}

export interface ReportTemplate {
  id: string;
  title: string;
  description: string;
  category: 'executive' | 'technical' | 'compliance' | 'incident';
  sections: string[];
}

export interface ReportHistory {
  id: string;
  title: string;
  created_at: string;
  type: string;
  status: 'generating' | 'completed' | 'failed';
  url: string;
  format: 'pdf' | 'docx' | 'csv';
}

export interface AIMessageCitation {
  marker: number;
  document_id: string | null;
  chunk_id: string | null;
  title: string;
  source: string;
  page: number | null;
  heading: string | null;
  chunk_index: number | null;
  score: number;
}

export interface AIMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp: string;
  mode?: 'fast' | 'deep';
  provider?: string;
  confidence?: number;
  sources?: string[];
  suggested_actions?: string[];
  mitre_techniques?: string[];
  /** Real knowledge-base citations (Phase 2.6 RAG) - empty when the answer
   * is not grounded in the knowledge base. */
  citations?: AIMessageCitation[];
  grounded?: boolean;
}

export interface AuditEvent {
  id: string;
  user_email: string;
  action: string;
  target: string;
  timestamp: string;
  request_id: string;
  details: string;
}

export interface ServiceStatus {
  name: string;
  status: 'healthy' | 'degraded' | 'unavailable' | 'unknown';
  latency: number;
  message?: string;
}
