"""Local Entity Extraction for RAG Local-First.

Extracts cybersecurity entities deterministically using regex/parsers:
CVE, IPv4, IPv6, Domain, URL, Email, Hashes, MITRE ATT&CK IDs, Ports,
Protocols, CVSS, Severity, and Application Resource IDs (AST, INC, ALT, VULN, REP).
"""

import re
from dataclasses import dataclass, field
from typing import List, Set


_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
)
_IPV6_RE = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|\b(?:[0-9a-fA-F]{1,4}:){1,7}:|:(?::[0-9a-fA-F]{1,4}){1,7}\b"
)
_URL_RE = re.compile(r"\bhttps?://[^\s<>\"]+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:com|net|org|io|gov|edu|mil|co|info|biz|vn|local|invalid)\b",
    re.IGNORECASE,
)
_MD5_RE = re.compile(r"\b[a-fA-F0-9]{32}\b")
_SHA1_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")
_SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
_MITRE_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)
_PORT_RE = re.compile(r"\bport\s+(\d{1,5})\b|\b:(\d{1,5})\b", re.IGNORECASE)
_CVSS_RE = re.compile(
    r"\bcvss\s*(?:v[23]\.\d\s*)?(?:score\s*)?([0-9]\.[0-9]|10\.0)\b", re.IGNORECASE
)
_SEVERITY_RE = re.compile(r"\b(critical|high|medium|low|info|informational)\b", re.IGNORECASE)
_PROTOCOL_RE = re.compile(r"\b(tcp|udp|icmp|http|https|ssh|ftp|dns|smtp|rdp|smb)\b", re.IGNORECASE)

# App specific entities
_ASSET_ID_RE = re.compile(r"\bAST-[A-Za-z0-9\-]+\b|\basset-[A-Za-z0-9\-]+\b", re.IGNORECASE)
_INCIDENT_ID_RE = re.compile(r"\bINC-[A-Za-z0-9\-]+\b|\bincident-[A-Za-z0-9\-]+\b", re.IGNORECASE)
_ALERT_ID_RE = re.compile(r"\bALT-[A-Za-z0-9\-]+\b|\balert-[A-Za-z0-9\-]+\b", re.IGNORECASE)
_VULN_ID_RE = re.compile(r"\bVULN-[A-Za-z0-9\-]+\b|\bvulnerability-[A-Za-z0-9\-]+\b", re.IGNORECASE)
_REPORT_ID_RE = re.compile(r"\bREP-[A-Za-z0-9\-]+\b|\breport-[A-Za-z0-9\-]+\b", re.IGNORECASE)


@dataclass
class ExtractedEntities:
    cves: List[str] = field(default_factory=list)
    ipv4s: List[str] = field(default_factory=list)
    ipv6s: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    hashes: List[str] = field(default_factory=list)
    mitre_ids: List[str] = field(default_factory=list)
    ports: List[str] = field(default_factory=list)
    protocols: List[str] = field(default_factory=list)
    cvss_scores: List[str] = field(default_factory=list)
    severities: List[str] = field(default_factory=list)
    asset_ids: List[str] = field(default_factory=list)
    incident_ids: List[str] = field(default_factory=list)
    alert_ids: List[str] = field(default_factory=list)
    vuln_ids: List[str] = field(default_factory=list)
    report_ids: List[str] = field(default_factory=list)

    @property
    def has_exact_entity(self) -> bool:
        """True if any high-confidence structural entity is present."""
        return bool(
            self.cves
            or self.ipv4s
            or self.ipv6s
            or self.urls
            or self.hashes
            or self.mitre_ids
            or self.asset_ids
            or self.incident_ids
            or self.alert_ids
            or self.vuln_ids
            or self.report_ids
        )

    def all_exact_terms(self) -> List[str]:
        """Flatten exact match terms for hybrid retrieval."""
        terms: Set[str] = set()
        terms.update(self.cves)
        terms.update(self.ipv4s)
        terms.update(self.ipv6s)
        terms.update(self.urls)
        terms.update(self.domains)
        terms.update(self.hashes)
        terms.update(self.mitre_ids)
        terms.update(self.asset_ids)
        terms.update(self.incident_ids)
        terms.update(self.alert_ids)
        terms.update(self.vuln_ids)
        terms.update(self.report_ids)
        return list(terms)


def extract_entities(text: str) -> ExtractedEntities:
    """Extract structured entities from input text."""
    if not text:
        return ExtractedEntities()

    raw = text.strip()

    cves = [m.group(0).upper() for m in _CVE_RE.finditer(raw)]
    ipv4s = [m.group(0) for m in _IPV4_RE.finditer(raw)]
    ipv6s = [m.group(0) for m in _IPV6_RE.finditer(raw)]
    urls = [m.group(0) for m in _URL_RE.finditer(raw)]
    emails = [m.group(0) for m in _EMAIL_RE.finditer(raw)]

    # Domains (exclude URLs)
    domains = [
        m.group(0).lower()
        for m in _DOMAIN_RE.finditer(raw)
        if not any(m.group(0) in url for url in urls)
    ]

    # Hashes
    hashes_set: Set[str] = set()
    for pattern in (_SHA256_RE, _SHA1_RE, _MD5_RE):
        for m in pattern.finditer(raw):
            hashes_set.add(m.group(0).lower())
    hashes = list(hashes_set)

    mitre_ids = [m.group(0).upper() for m in _MITRE_RE.finditer(raw)]

    ports: List[str] = []
    for m in _PORT_RE.finditer(raw):
        p = m.group(1) or m.group(2)
        if p:
            ports.append(p)

    protocols = list({m.group(0).upper() for m in _PROTOCOL_RE.finditer(raw)})
    cvss_scores = [m.group(1) for m in _CVSS_RE.finditer(raw)]
    severities = list({m.group(0).lower() for m in _SEVERITY_RE.finditer(raw)})

    asset_ids = [m.group(0) for m in _ASSET_ID_RE.finditer(raw)]
    incident_ids = [m.group(0) for m in _INCIDENT_ID_RE.finditer(raw)]
    alert_ids = [m.group(0) for m in _ALERT_ID_RE.finditer(raw)]
    vuln_ids = [m.group(0) for m in _VULN_ID_RE.finditer(raw)]
    report_ids = [m.group(0) for m in _REPORT_ID_RE.finditer(raw)]

    return ExtractedEntities(
        cves=list(dict.fromkeys(cves)),
        ipv4s=list(dict.fromkeys(ipv4s)),
        ipv6s=list(dict.fromkeys(ipv6s)),
        urls=list(dict.fromkeys(urls)),
        domains=list(dict.fromkeys(domains)),
        emails=list(dict.fromkeys(emails)),
        hashes=hashes,
        mitre_ids=list(dict.fromkeys(mitre_ids)),
        ports=list(dict.fromkeys(ports)),
        protocols=protocols,
        cvss_scores=list(dict.fromkeys(cvss_scores)),
        severities=severities,
        asset_ids=list(dict.fromkeys(asset_ids)),
        incident_ids=list(dict.fromkeys(incident_ids)),
        alert_ids=list(dict.fromkeys(alert_ids)),
        vuln_ids=list(dict.fromkeys(vuln_ids)),
        report_ids=list(dict.fromkeys(report_ids)),
    )
