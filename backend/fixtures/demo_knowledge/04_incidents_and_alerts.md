# Incidents and Alerts (Demo)

Fabricated incident records for Meridian Financial Group, consistent with
the asset inventory and CVE records in this knowledge pack.

## INC-2031: Log4Shell exploitation attempt against portal.meridian.example

- Date: 2025-12-19 (one day before remediation completed).
- Severity: Critical.
- Affected asset: portal.meridian.example.
- Related CVE: CVE-2021-44228 (Log4Shell).
- MITRE ATT&CK technique: T1190 (Exploit Public-Facing Application).
- Detection source: fw-edge-01.meridian.internal WAF logs - a JNDI lookup
  pattern in an HTTP request header was flagged and blocked.
- Timeline:
  - 14:02 UTC: WAF detects and blocks a JNDI lookup pattern targeting
    portal.meridian.example.
  - 14:07 UTC: SOC analyst triages the alert, confirms the request was
    blocked (not executed) and escalates to Critical per the Incident
    Response Policy's 1-hour SLA.
  - 15:40 UTC: Containment complete - portal.meridian.example's Log4j
    dependency confirmed vulnerable; emergency patch scheduled.
  - 2025-12-20: Remediation complete (Log4j upgraded).
- Outcome: No code execution occurred - the WAF blocked the request before
  it reached the vulnerable Log4j component. No data exfiltration was
  detected or confirmed.
- Root cause: portal.meridian.example was running a version of Apache
  Log4j vulnerable to CVE-2021-44228 at the time of the attempt.

## INC-2044: Suspicious PowerShell execution on ws-analyst07.meridian.internal

- Date: 2026-03-02.
- Severity: High.
- Affected asset: ws-analyst07.meridian.internal.
- MITRE ATT&CK technique: T1059.001 (Command and Scripting Interpreter:
  PowerShell).
- Detection source: EDR agent on ws-analyst07.meridian.internal.
- Timeline:
  - 09:14 UTC: A SOC analyst opens an email attachment that turns out to be
    a phishing lure (see the Phishing Response Playbook for the standard
    procedure this incident followed).
  - 09:15 UTC: The attachment spawns an obfuscated PowerShell process; EDR
    on ws-analyst07.meridian.internal flags and blocks the execution
    automatically before any further action completes.
  - 09:20 UTC: SOC escalates per policy (High severity, 4-hour SLA),
    isolates the workstation from the network as a precaution.
  - 11:00 UTC: Investigation confirms EDR blocked the payload before any
    credential access or lateral movement occurred.
- Outcome: No credentials were compromised. The workstation was reimaged as
  a precaution before being returned to service.
- Root cause: A phishing email bypassed initial email filtering and reached
  the analyst's inbox.

## Alert Volume Summary (last 90 days, demo data)

- Critical alerts: 1 (INC-2031).
- High alerts: 1 (INC-2044).
- Medium/Low alerts: routine SOC noise, not individually documented here.
