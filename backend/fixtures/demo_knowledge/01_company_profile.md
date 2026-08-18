# Meridian Financial Group - Company Security Profile

Meridian Financial Group is a fictional regional bank and fintech provider
used for demo purposes only, with approximately 1,200 employees. This
profile, and every other document in this demo knowledge pack, describes a
fabricated scenario for testing and demonstration - no real company,
person, or incident is represented.

## Organization

- Headquarters: Meridian Tower, demo-only address.
- Business units: Retail Banking, Payments Processing, Corporate IT,
  Security Operations Center (SOC).
- Regulatory scope: PCI-DSS (payments processing), regional banking
  regulations.

## Key Systems

| System | Hostname | Role | Criticality |
|---|---|---|---|
| Domain Controller | dc-01.meridian.internal | Active Directory, authentication | Critical |
| Edge Firewall | fw-edge-01.meridian.internal | Perimeter network defense | Critical |
| Customer Portal | portal.meridian.example | Public-facing customer web app (Apache-based) | Critical |
| Payments Database | db-payments-01.meridian.internal | Payments processing, PCI-DSS scope | Critical |
| Analyst Workstation | ws-analyst07.meridian.internal | SOC analyst endpoint | Medium |

## Security Organization

The Security Operations Center (SOC) operates 24/7 and is responsible for
monitoring, incident response, and vulnerability management. The Chief
Information Security Officer (CISO) has final sign-off authority on risk
acceptance decisions above a risk score of 70 (see the Risk Acceptance
Policy document in this knowledge pack).

## Technology Stack

- Perimeter: fw-edge-01.meridian.internal (edge firewall, WAF enabled).
- Identity: dc-01.meridian.internal (Active Directory domain controller).
- Web: portal.meridian.example (customer-facing portal, historically ran a
  vulnerable Apache Log4j version - see the CVE and Vulnerability Records
  document).
- Endpoint: EDR deployed fleet-wide, including ws-analyst07.meridian.internal.
