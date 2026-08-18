import { apiGet, apiPost } from './client';

export type AttackNodeType = 'attacker' | 'asset' | 'database' | 'gateway' | 'target';
export type AttackNodeStatus = 'compromised' | 'vulnerable' | 'secure';
export type AttackEdgeStatus = 'active' | 'potential' | 'blocked';
export type AttackSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface AttackGraphNode {
  id: string;
  node_type: AttackNodeType;
  label: string;
  ip_address: string;
  status: AttackNodeStatus;
  severity: AttackSeverity;
  description: string;
  cves: string[];
  position_x: number;
  position_y: number;
  created_at: string;
  updated_at: string;
}

export interface AttackGraphEdge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  label: string;
  status: AttackEdgeStatus;
  created_at: string;
  updated_at: string;
}

export interface AttackGraph {
  nodes: AttackGraphNode[];
  edges: AttackGraphEdge[];
}

export interface AttackNodeInput {
  node_type: AttackNodeType;
  label: string;
  ip_address?: string;
  status: AttackNodeStatus;
  severity: AttackSeverity;
  description?: string;
  cves?: string[];
  position_x?: number;
  position_y?: number;
}

export interface AttackEdgeInput {
  source_node_id: string;
  target_node_id: string;
  label: string;
  status?: AttackEdgeStatus;
}

export function getAttackGraph(): Promise<AttackGraph> {
  return apiGet<AttackGraph>('/api/attack-graph');
}

export function createAttackNode(input: AttackNodeInput): Promise<AttackGraphNode> {
  return apiPost<AttackGraphNode>('/api/attack-graph/nodes', input);
}

export function createAttackEdge(input: AttackEdgeInput): Promise<AttackGraphEdge> {
  return apiPost<AttackGraphEdge>('/api/attack-graph/edges', input);
}

export function generateAttackGraphFromIncident(incidentId: string): Promise<AttackGraph> {
  return apiPost<AttackGraph>(`/api/attack-graph/generate-from-incident/${incidentId}`);
}
