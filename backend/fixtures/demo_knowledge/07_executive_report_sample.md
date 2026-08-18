# Executive Security Summary - Q1 2026 (Demo Sample Report)

Prepared for: Meridian Financial Group executive leadership (fabricated
demo report).

## Summary

During the reporting period, the Security Operations Center handled two
notable incidents, both contained without confirmed data loss or
compromise:

1. **INC-2031** (2025-12-19, Critical): A Log4Shell (CVE-2021-44228)
   exploitation attempt against the customer portal (portal.meridian.example)
   was blocked at the perimeter firewall/WAF before any code execution
   occurred. The underlying vulnerability was remediated the following day.
2. **INC-2044** (2026-03-02, High): A phishing email led to an obfuscated
   PowerShell execution attempt on an analyst workstation
   (ws-analyst07.meridian.internal), which was blocked automatically by
   endpoint detection and response (EDR) tooling. No credentials were
   compromised.

## Risk Posture

Both critical CVEs tracked against Meridian assets this period
(CVE-2021-44228 on portal.meridian.example, CVE-2020-1472 on
dc-01.meridian.internal) are now fully remediated. No open critical or high
vulnerability currently has an approved risk acceptance.

## Recommended Actions

1. Continue quarterly phishing-simulation training for all staff, with
   particular focus on the SOC team given INC-2044's initial vector.
2. Extend WAF rule coverage that successfully blocked INC-2031 to all
   internet-facing applications, not just portal.meridian.example.
3. Re-validate that db-payments-01.meridian.internal (PCI-DSS scope) is not
   reachable from any host outside the internal payments segment, as a
   preventative measure against a future ransomware scenario (see the
   Ransomware Response Playbook).

## Sources

This report synthesizes information from: the Incidents and Alerts
document, the CVE and Vulnerability Records document, the Asset Inventory,
and the MITRE ATT&CK Technique Reference, all part of this knowledge pack.
