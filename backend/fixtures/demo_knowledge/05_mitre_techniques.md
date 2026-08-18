# MITRE ATT&CK Technique Reference (Demo)

Real MITRE ATT&CK technique definitions, referenced by the fabricated
incidents in this knowledge pack. Technique descriptions are factual and
summarized from the public MITRE ATT&CK framework; the mapping to
Meridian's specific incidents is fabricated demo data.

## T1190: Exploit Public-Facing Application

- Tactic: Initial Access.
- Description: Adversaries exploit a weakness in an internet-facing
  computer or program to gain initial access, using software bugs,
  glitches, or configuration issues in an application exposed to the
  internet.
- Observed at Meridian: INC-2031 (Log4Shell exploitation attempt against
  portal.meridian.example, blocked before code execution).

## T1059.001: Command and Scripting Interpreter - PowerShell

- Tactic: Execution.
- Description: Adversaries abuse PowerShell commands and scripts for
  execution, given its deep integration with the Windows operating system
  and prevalence in legitimate administration.
- Observed at Meridian: INC-2044 (obfuscated PowerShell spawned by a
  phishing attachment on ws-analyst07.meridian.internal, blocked by EDR).

## T1078: Valid Accounts

- Tactic: Defense Evasion, Persistence, Privilege Escalation, Initial
  Access.
- Description: Adversaries obtain and abuse credentials of existing
  accounts as a means of gaining initial access, persistence, privilege
  escalation, or defense evasion.
- Observed at Meridian: Not observed in any confirmed incident - this
  technique is tracked as a mapping for CVE-2020-1472 (Zerologon), which
  was patched proactively and never exploited against dc-01.meridian.internal.

## T1486: Data Encrypted for Impact

- Tactic: Impact.
- Description: Adversaries encrypt data on target systems or on large
  numbers of systems in a network to interrupt availability, typically
  followed by a ransom demand (ransomware).
- Observed at Meridian: Not observed in any incident to date. Tracked here
  because it is the primary technique the Ransomware Response Playbook (see
  the Playbooks and Policies document) is written to address.
