import { apiGet, apiPost } from './client';

export interface DemoChain {
  active: boolean;
  isolation: string;
  asset: null | { id: string; name: string; hostname: string };
  vulnerability: null | { id: string; cve_id: string; title: string };
  alert: null | { id: string; title: string; severity: string };
  incident: null | { id: string; title: string; severity: string };
  mitre: Array<{ id: string; technique_id: string; name: string }>;
  routes: Record<string, string>;
}

export function getDemoStatus(): Promise<DemoChain> {
  return apiGet<DemoChain>('/api/demo/status');
}

export function startDemoMode(): Promise<DemoChain> {
  return apiPost<DemoChain>('/api/demo/start', {});
}

export interface DemoResetResult extends DemoChain {
  deleted: Record<string, number>;
}

export function resetDemoMode(): Promise<DemoResetResult> {
  return apiPost<DemoResetResult>('/api/demo/reset', {});
}
