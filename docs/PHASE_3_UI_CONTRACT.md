# Phase 3 UI Data Contract Specification

This document details the frontend data interfaces and mock data contracts defined in Phase 3 of the CyberSec Assistant.

---

## 1. Core Data Models

### Threat Intelligence & Indicators of Compromise (IOC)
The frontend components in the Threat Intelligence matrix rely on the following typed contract:

```typescript
export type IOCType = 'ip' | 'domain' | 'url' | 'sha256' | 'md5';

export interface IOC {
  id: string;              // Unique identifier (e.g. ioc-1)
  value: string;           // The indicator value (e.g. IP, domain name, hash)
  type: IOCType;           // Indicator type classification
  severity: 'low' | 'medium' | 'high' | 'critical';
  description: string;     // Narrative description of origin/threat
  first_seen: string;      // ISO-8601 timestamp
  last_seen: string;       // ISO-8601 timestamp
  watchlist: boolean;      // True if monitored on the watchlist
  related_incidents?: string[]; // IDs of linked incidents
}

export interface IOCRelation {
  source: string;          // Source IOC ID
  target: string;          // Target IOC ID
  type: string;            // Relationship type (e.g., resolves_to, downloaded_from)
}
```

### Asset Management
Used in Asset Inventory and Asset Profile views:

```typescript
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
```

### Vulnerability Center
Vulnerability details and patch tracking schemas:

```typescript
export interface Vulnerability {
  id: string;              // CVE ID (e.g. CVE-2021-44228)
  title: string;           // Human-readable summary
  description: string;     // Detailed advisory description
  cvss: number;            // CVSS numerical score
  severity: 'low' | 'medium' | 'high' | 'critical';
  published_date: string;  // ISO-8601 date
  updated_date: string;    // ISO-8601 date
  references: string[];    // Array of advisory URLs
  affected_products: string[]; // List of package and OS names
  remediation?: string;    // Actionable mitigation advice
}

export interface PatchTracking {
  id: string;              // Unique patch track ID
  cve_id: string;          // Vulnerability CVE ID
  asset_id: string;        // Asset ID undergoing patching
  status: 'not_started' | 'in_progress' | 'patched';
  updated_at: string;      // ISO-8601 timestamp
}
```

---

## 2. API & Data Provider Interfaces
The `FixtureDataProvider` namespace exposes asynchronous operations resolving these contract boundaries:

* **`getUserByEmail(email: string): Promise<User | null>`**: Checks mock credentials and returns profile configurations.
* **`getChatThreads(): Promise<ChatThread[]>`**: Returns conversational threads containing security assistant prompts and responses.
* **`getAssets(): Promise<Asset[]>`**: Fetches all monitored assets.
* **`getAlerts(): Promise<Alert[]>`**: Fetches system alerts.
* **`getIncidents(): Promise<Incident[]>`**: Fetches escalated incidents.
* **`getPasswordFeedback(strength: string): Promise<PasswordStrengthResult | null>`**: Provides standard local feedback rules based on input parameters.
* **`getUrlScanResult(url: string): Promise<URLScanResult | null>`**: Simulates reputation logs and threat categories for analyzed URLs.
* **`getServiceHealth(): Promise<ServiceStatus[]>`**: Delivers real-time probe statuses for operational sub-components.

---

## 3. Pagination Envelope Contract

For endpoints returning list structures (e.g. `/api/v1/assets`, `/api/v1/threats/iocs`), the API payload utilizes a standard envelope format:

```typescript
export interface PaginatedEnvelope<T> {
  items: T[];              // Data records array
  page: number;            // 1-indexed current page number
  page_size: number;       // Number of items per page
  total_items: number;     // Aggregate count matching filters
  total_pages: number;     // Aggregate pages count
}
```

