"""ORM models.

Importing this package registers every model on ``Base.metadata``, which is
what ``alembic/env.py`` and the test-suite schema bootstrap rely on.
"""
from backend.database.models.asset import Asset
from backend.database.models.alert import AlertRecord
from backend.database.models.attack_graph import AttackGraphEdge, AttackGraphNode
from backend.database.models.conversation import Conversation, Message
from backend.database.models.finding import Finding, FindingTransition
from backend.database.models.incident import IncidentRecord, IncidentTask, IncidentTimelineEvent
from backend.database.models.knowledge import KnowledgeChunk, KnowledgeDocument
from backend.database.models.mitre import MitreTechniqueCoverage
from backend.database.models.notification import NotificationRecord
from backend.database.models.project import Project, ProjectMember
from backend.database.models.rbac import AdminAuditLog, LocalAdminCredential, UserRole
from backend.database.models.report import ReportRecord
from backend.database.models.scan import ScanRun
from backend.database.models.scan_history import SecurityScanRecord
from backend.database.models.security_news import SecurityNewsArticle
from backend.database.models.threat_intel import ThreatIOC
from backend.database.models.vulnerability import VulnerabilityPatchTask, VulnerabilityRecord
from backend.database.models.workspace import Workspace, WorkspaceMember

__all__ = [
    "Conversation",
    "Message",
    "SecurityScanRecord",
    "SecurityNewsArticle",
    "ReportRecord",
    "NotificationRecord",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "UserRole",
    "LocalAdminCredential",
    "AdminAuditLog",
    "Asset",
    "AlertRecord",
    "AttackGraphNode",
    "AttackGraphEdge",
    "IncidentRecord",
    "IncidentTask",
    "IncidentTimelineEvent",
    "MitreTechniqueCoverage",
    "ThreatIOC",
    "VulnerabilityRecord",
    "VulnerabilityPatchTask",
    "Workspace",
    "WorkspaceMember",
    "Project",
    "ProjectMember",
    "ScanRun",
    "Finding",
    "FindingTransition",
]
