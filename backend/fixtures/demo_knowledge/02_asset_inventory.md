# Asset Inventory (Demo)

Fabricated asset inventory for Meridian Financial Group, consistent with
the Company Security Profile document in this knowledge pack.

## Critical Assets

### dc-01.meridian.internal
- Type: Domain Controller (Windows Server, Active Directory)
- Owner: Corporate IT
- Business criticality: Critical
- Patch status: Patched (Zerologon, CVE-2020-1472, remediated 2026-02-14)
- Notes: Single authoritative AD domain controller for the internal network.

### fw-edge-01.meridian.internal
- Type: Network device (perimeter firewall / WAF)
- Owner: SOC
- Business criticality: Critical
- Patch status: Patched, firmware current
- Notes: All inbound traffic to portal.meridian.example passes through
  this device; WAF logs are the primary detection source for
  application-layer attacks.

### portal.meridian.example
- Type: Cloud resource (public-facing web application, Apache-based)
- Owner: Payments Processing
- Business criticality: Critical
- Patch status: Patched (Log4Shell, CVE-2021-44228, remediated 2025-12-20)
- Notes: Customer-facing login and account management portal. Historically
  ran a vulnerable bundled Apache Log4j library until the 2025-12-20 patch.

### db-payments-01.meridian.internal
- Type: Database server
- Owner: Payments Processing
- Business criticality: Critical
- Patch status: Patched
- Notes: PCI-DSS scope. Not directly internet-facing; only reachable from
  portal.meridian.example over an internal segment.

## Medium Criticality Assets

### ws-analyst07.meridian.internal
- Type: Workstation
- Owner: SOC (assigned to a security analyst)
- Business criticality: Medium
- Patch status: Patched, EDR agent active
- Notes: Source workstation involved in incident INC-2044 (see Incidents
  and Alerts document).
