# Incident Response Playbooks and Policies (Demo)

## Incident Response Policy

Severity levels and response SLAs:

| Severity | Initial response SLA | Example |
|---|---|---|
| Critical | 1 hour | Confirmed exploitation of a public-facing critical asset (e.g. INC-2031) |
| High | 4 hours | Suspicious execution on an endpoint with EDR containment (e.g. INC-2044) |
| Medium | 24 hours | Isolated suspicious activity with no confirmed impact |
| Low | Best-effort | Informational alerts, routine SOC noise |

Every incident must be logged with: detection source, timeline, affected
assets, MITRE ATT&CK technique mapping, containment actions, and root
cause. Incidents are not closed until root cause is documented.

## Risk Acceptance Policy

- A risk finding with a risk score of 70 or above requires the Chief
  Information Security Officer's (CISO) explicit sign-off before it may be
  formally accepted (as opposed to remediated).
- A risk score below 70 may be accepted by the asset owner's department
  head, with the acceptance decision and rationale documented.
- All risk acceptances are reviewed quarterly and must be re-justified or
  remediated.

## Phishing Response Playbook

1. Isolate the affected endpoint from the network immediately upon
   confirmation of a malicious attachment or link having been opened.
2. Preserve the original email (headers included) for analysis - do not
   forward it in a way that could re-trigger the payload.
3. Check EDR/AV logs on the affected endpoint for any process execution
   tied to the attachment or link.
4. If credential entry is suspected, force a password reset for the
   affected account and review authentication logs for anomalous logins.
5. Notify affected users and, if the campaign appears targeted at multiple
   employees, issue an organization-wide alert.
6. Document the incident per the Incident Response Policy above, including
   the MITRE ATT&CK technique(s) involved (commonly T1566 for the phishing
   delivery itself, plus whatever technique the payload attempted - e.g.
   T1059.001 for a PowerShell payload, as in INC-2044).

## Ransomware Response Playbook

1. Immediately isolate affected systems from the network - do not power
   them off (memory forensics may be needed), disconnect network access
   instead.
2. Identify the ransomware family if possible, and check for known
   decryption tools before considering any other option.
3. Assess the blast radius: which systems, shares, and backups are
   affected or reachable from the initial infection point.
4. Verify backup integrity for critical systems (see the asset inventory's
   criticality ratings - dc-01, fw-edge-01, portal.meridian.example, and
   db-payments-01 are all Critical and must be prioritized).
5. Engage executive leadership and legal/compliance immediately - a
   ransomware incident affecting PCI-DSS-scoped systems (db-payments-01)
   has regulatory notification implications.
6. Do not pay a ransom without executive and legal sign-off; this decision
   is never made unilaterally by the SOC.
7. This playbook maps to MITRE ATT&CK technique T1486 (Data Encrypted for
   Impact) - see the MITRE Technique Reference document.
