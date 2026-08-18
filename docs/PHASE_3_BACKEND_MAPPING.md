# Phase 3 UI-to-Backend Field Mapping Spec

This document details the mapping between Phase 3 UI properties and their corresponding backend database models or API fields.

---

## 1. Threats & IOC Mapping
* **API Endpoint**: `/api/v1/threats/iocs`
* **HTTP Methods**: `GET` (list/filter), `POST` (create), `GET /:id` (detail), `PUT /:id/watchlist` (toggle watchlist)

| UI Property | Backend DB Column / Field | Data Type | Notes |
|---|---|---|---|
| `id` | `id` | UUID / String | Unique indicator primary key |
| `value` | `indicator_value` | VARCHAR(255) | IP / Domain / URL string value |
| `type` | `indicator_type` | VARCHAR(50) | Enum constraint: `ip`, `domain`, `url`, `sha256`, `md5` |
| `severity` | `severity_level` | VARCHAR(50) | Enum: `low`, `medium`, `high`, `critical` |
| `description` | `description` | TEXT | Detailed threat context |
| `first_seen` | `first_seen_at` | TIMESTAMP | ISO-8601 UTC timestamp |
| `last_seen` | `last_seen_at` | TIMESTAMP | ISO-8601 UTC timestamp |
| `watchlist` | `is_watchlist` | BOOLEAN | Watchlist subscription state flag |

---

## 2. Asset Management Mapping
* **API Endpoint**: `/api/v1/assets`
* **HTTP Methods**: `GET` (list/filter), `POST` (create), `GET /:id` (detail), `PUT /:id` (update), `DELETE /:id` (remove)

| UI Property | Backend DB Column / Field | Data Type | Notes |
|---|---|---|---|
| `id` | `asset_uuid` | UUID | Primary key |
| `name` | `asset_name` | VARCHAR(100) | Label |
| `type` | `device_type` | VARCHAR(50) | Enum: `server`, `workstation`, `cloud_resource`, etc. |
| `hostname` | `fqdn` | VARCHAR(255) | Fully Qualified Domain Name |
| `ip_address` | `ipv4_address` | VARCHAR(45) | IPv4 or IPv6 string |
| `operating_system`| `os_version` | VARCHAR(100) | OS version name |
| `owner` | `custodian` | VARCHAR(100) | Person responsible for asset |
| `department` | `org_unit` | VARCHAR(100) | Department |
| `business_criticality`| `criticality` | VARCHAR(50) | Enum: `low`, `medium`, `high`, `critical` |
| `internet_exposed`| `is_internet_facing`| BOOLEAN | Exposed state flag |
| `description` | `notes` | TEXT | Description |
| `linked_cves` | `cve_ids` | ARRAY[VARCHAR] | List of linked CVE string keys |

---

## 3. Vulnerability Center Mapping
* **API Endpoint**: `/api/v1/vulnerabilities`
* **HTTP Methods**: `GET` (list), `GET /:id` (detail)

| UI Property | Backend DB Column / Field | Data Type | Notes |
|---|---|---|---|
| `id` | `cve_id` | VARCHAR(30) | Natural Primary Key (e.g. `CVE-2021-44228`) |
| `title` | `summary` | VARCHAR(255) | Short title |
| `description` | `detail_description` | TEXT | Full description text |
| `cvss` | `cvss_score` | DECIMAL(3, 1) | Float (0.0 to 10.0) |
| `severity` | `severity_bucket` | VARCHAR(20) | Calculated bucket: `low`, `medium`, `high`, `critical` |
| `published_date` | `nvd_published_at` | TIMESTAMP | ISO-8601 UTC timestamp |
| `updated_date` | `nvd_updated_at` | TIMESTAMP | ISO-8601 UTC timestamp |
| `references` | `advisory_references`| JSONB / List | Array of links |
| `affected_products`| `affected_packages` | JSONB / List | Array of platforms and packages |
| `remediation` | `mitigation_steps` | TEXT | Mitigation guidelines |
