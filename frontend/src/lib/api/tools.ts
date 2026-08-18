import { apiGet, apiPost } from './client';

export interface UrlScanFinding {
  code: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  message: string;
  weight: number;
}

/** VirusTotal's verdict, kept entirely separate from the local heuristic
 * `findings`/`risk_score` above - a clean local scan and an absent/
 * unavailable VirusTotal verdict must never be displayed as "confirmed
 * safe" together. */
export interface UrlReputationResult {
  configured: boolean;
  status: 'completed' | 'pending' | 'not_configured' | 'unavailable';
  malicious: number;
  suspicious: number;
  harmless: number;
  undetected: number;
  permalink: string | null;
  error_category: 'NOT_CONFIGURED' | 'INVALID_KEY' | 'RATE_LIMITED' | 'UNAVAILABLE' | 'DEGRADED' | null;
}

export interface UrlScanResponse {
  id: string;
  url: string;
  normalized_url: string;
  hostname: string;
  port: number;
  scheme: 'http' | 'https';
  has_https: boolean;
  reachable: boolean;
  status: 'safe' | 'suspicious' | 'critical' | 'failed';
  risk_score: number;
  severity: 'low' | 'medium' | 'high' | 'critical';
  http_status: number | null;
  final_url: string | null;
  redirect_chain: string[];
  redirect_count: number;
  headers: Record<string, string>;
  body_truncated: boolean;
  failure_reason: string | null;
  findings: UrlScanFinding[];
  recommendations: string[];
  reputation: UrlReputationResult;
  duration_ms: number;
  created_at: string;
}

export function scanUrl(url: string): Promise<UrlScanResponse> {
  return apiPost<UrlScanResponse>('/api/tools/url-scan', { url });
}

export interface PasswordCheckResponse {
  strength: 'weak' | 'medium' | 'strong' | 'very_strong';
  score: number;
  length: number;
  entropy_bits: number;
  crack_time: string;
  has_lowercase: boolean;
  has_uppercase: boolean;
  has_digits: boolean;
  has_special: boolean;
  character_classes: number;
  longest_repeat_run: number;
  longest_sequential_run: number;
  has_repeated_block: boolean;
  is_common: boolean;
  warnings: string[];
  recommendations: string[];
}

/** The password is sent to /api/tools/password-check for analysis only -
 * never persisted, logged, or stored by this client either. */
export function checkPasswordStrength(password: string): Promise<PasswordCheckResponse> {
  return apiPost<PasswordCheckResponse>('/api/tools/password-check', { password });
}

export interface PasswordGuidanceResponse {
  strength: 'weak' | 'medium' | 'strong' | 'very_strong';
  headline: string;
  feedback: string;
  recommendations: string[];
}

export function getPasswordGuidance(
  strength: 'weak' | 'medium' | 'strong' | 'very_strong',
): Promise<PasswordGuidanceResponse> {
  return apiGet<PasswordGuidanceResponse>(`/api/tools/password-guidance?strength=${strength}`);
}
