import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { isSupabaseConfigured } from '../lib/supabase/authService';
import { AppShell } from '../layouts/AppShell';
import { LoginView } from '../features/auth/login/LoginView';
import { RegisterView } from '../features/auth/register/RegisterView';
import { ForgotPasswordView } from '../features/auth/forgot-password/ForgotPasswordView';
import { ResetPasswordView } from '../features/auth/reset-password/ResetPasswordView';
import { DashboardView } from '../features/dashboard/DashboardView';
import { AccessDeniedView } from '../features/auth/login/AccessDeniedView';
import { OfflineView } from '../features/auth/login/OfflineView';
import { AdminOverviewView } from '../features/admin/views/AdminOverviewView';
import { UserManagementView } from '../features/admin/views/UserManagementView';
import { AdminAuditView } from '../features/admin/views/AdminAuditView';
// Task 7: Admin Console Upgrade - vuln-lifecycle admin visibility tabs.
import { AdminWorkspacesView } from '../features/admin/views/AdminWorkspacesView';
import { AdminProjectsView } from '../features/admin/views/AdminProjectsView';
import { AdminFindingsView } from '../features/admin/views/AdminFindingsView';
import { AdminSlaPoliciesView } from '../features/admin/views/AdminSlaPoliciesView';

// Phase 2 View imports
import { AIAssistantView } from '../features/assistant/views/AIAssistantView';
import { URLScannerView } from '../features/security-toolkit/url-scanner/views/URLScannerView';
import { PasswordCheckerView } from '../features/security-toolkit/password-checker/views/PasswordCheckerView';
import { CVELookupView } from '../features/security-toolkit/cve-lookup/views/CVELookupView';
import { ScanHistoryView } from '../features/security-toolkit/scan-history/views/ScanHistoryView';
import { KnowledgeBaseView } from '../features/knowledge-base/views/KnowledgeBaseView';

// Phase 3 View imports
import { ThreatIntelView } from '../features/threat-intel/views/ThreatIntelView';
import { IOCListView } from '../features/threat-intel/views/IOCListView';
import { IOCDetailView } from '../features/threat-intel/views/IOCDetailView';
import { IOCGraphView } from '../features/threat-intel/views/IOCGraphView';
import { IOCWatchlistView } from '../features/threat-intel/views/IOCWatchlistView';
import { AssetInventoryView } from '../features/assets/views/AssetInventoryView';
import { AssetProfileView } from '../features/assets/views/AssetProfileView';
import { VulnerabilityListView } from '../features/vulnerabilities/views/VulnerabilityListView';
import { VulnerabilityDetailView } from '../features/vulnerabilities/views/VulnerabilityDetailView';
import { PatchTrackingView } from '../features/vulnerabilities/views/PatchTrackingView';
import { AlertsView } from '../features/alerts/views/AlertsView';
import { AlertDetailView } from '../features/alerts/views/AlertDetailView';
import { IncidentListView } from '../features/incidents/views/IncidentListView';
import { IncidentDetailView } from '../features/incidents/views/IncidentDetailView';
import { IncidentPlaybookView } from '../features/incidents/views/IncidentPlaybookView';
import { MitreMatrixView } from '../features/mitre/views/MitreMatrixView';
import { MitreTechniqueDetailView } from '../features/mitre/views/MitreTechniqueDetailView';
import { AttackGraphView } from '../features/attack-graph/views/AttackGraphView';
import { SecurityNewsView } from '../features/news/views/SecurityNewsView';
import { SecurityNewsDetailView } from '../features/news/views/SecurityNewsDetailView';
import { ReportsCenterView } from '../features/reports/views/ReportsCenterView';
import { ReportBuilderView } from '../features/reports/views/ReportBuilderView';
import { ReportHistoryView } from '../features/reports/views/ReportHistoryView';
import { NotFoundView } from '../features/errors/NotFoundView';
import { ServerErrorView } from '../features/errors/ServerErrorView';
import { ProfileView } from '../features/profile/ProfileView';
import { NotificationsView } from '../features/notifications/views/NotificationsView';
import { OnboardingView } from '../features/onboarding/views/OnboardingView';

// Vuln-lifecycle foundation — Task 1
import { WorkspaceListView } from '../features/workspaces/WorkspaceListView';
import { WorkspaceDetailView } from '../features/workspaces/WorkspaceDetailView';
import { WorkspaceFormView } from '../features/workspaces/WorkspaceFormView';
import { ProjectListView } from '../features/projects/ProjectListView';
import { ProjectDetailView } from '../features/projects/ProjectDetailView';
import { ProjectFormView } from '../features/projects/ProjectFormView';
import { FindingListView } from '../features/findings/FindingListView';
import { FindingDetailView } from '../features/findings/FindingDetailView';
import { MyTasksView } from '../features/findings/MyTasksView';

// Vuln-lifecycle foundation — Task 3 (SLA policies)
import { SlaPolicyView } from '../features/sla/SlaPolicyView';

// Router protection wrapper
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading } = useAuth();
  // Session restore (getSession()) is async - on a fresh page load `user`
  // starts null before it resolves. Redirecting immediately would bounce a
  // genuinely logged-in user back to /login on every reload.
  if (isLoading) {
    return null;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <AppShell>{children}</AppShell>;
};

// Admin protection wrapper
const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading } = useAuth();
  if (isLoading) {
    return null;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (user.role !== 'admin' && user.role !== 'super_admin') {
    return <Navigate to="/access-denied" replace />;
  }
  return <AppShell>{children}</AppShell>;
};

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      
      {/* Public Pages */}
      <Route path="/login" element={<LoginView />} />
      {/* Self-service registration only makes sense against a hosted
          Supabase project - this Docker-local / Demo Mode deployment has
          no Supabase configured and authenticates only the 5 seeded demo
          accounts (see backend/services/demo_accounts.py) plus the
          first-run admin bootstrap folded into /login. Rendering the
          register form here would submit against a Supabase client that
          doesn't exist and fail every time - a dead form, not a real
          feature - so redirect to /login instead, same pattern as
          /admin/login and /admin/setup below. */}
      <Route
        path="/register"
        element={isSupabaseConfigured() ? <RegisterView /> : <Navigate to="/login" replace />}
      />
      <Route path="/forgot-password" element={<ForgotPasswordView />} />
      <Route path="/reset-password" element={<ResetPasswordView />} />
      <Route path="/access-denied" element={<AccessDeniedView />} />
      <Route path="/offline" element={<OfflineView />} />

      {/* Deprecated: unified into the single /login page (which itself
          shows the first-run setup form when no administrator exists yet).
          Kept as redirects, not a hard 404, so an old bookmark/link still
          lands somewhere useful instead of breaking. */}
      <Route path="/admin/login" element={<Navigate to="/login" replace />} />
      <Route path="/admin/setup" element={<Navigate to="/login" replace />} />

      {/* Protected Operations Layout Wrapper */}
      <Route path="/dashboard" element={<ProtectedRoute><DashboardView /></ProtectedRoute>} />
      
      {/* AI Assistant */}
      <Route path="/ai" element={<ProtectedRoute><AIAssistantView /></ProtectedRoute>} />
      <Route path="/ai/knowledge" element={<ProtectedRoute><AIAssistantView /></ProtectedRoute>} />

      {/* Toolkit */}
      <Route path="/toolkit/url-scanner" element={<ProtectedRoute><URLScannerView /></ProtectedRoute>} />
      <Route path="/toolkit/password-checker" element={<ProtectedRoute><PasswordCheckerView /></ProtectedRoute>} />
      <Route path="/toolkit/cve-lookup" element={<ProtectedRoute><CVELookupView /></ProtectedRoute>} />
      <Route path="/toolkit/history" element={<ProtectedRoute><ScanHistoryView /></ProtectedRoute>} />

      {/* Knowledge Base — Phase 2.6 RAG */}
      <Route path="/knowledge-base" element={<ProtectedRoute><KnowledgeBaseView /></ProtectedRoute>} />
      <Route path="/knowledge-base/documents/:documentId" element={<ProtectedRoute><KnowledgeBaseView /></ProtectedRoute>} />

      {/* Threat Intel — Phase 3 */}
      <Route path="/threat-intelligence" element={<ProtectedRoute><ThreatIntelView /></ProtectedRoute>} />
      <Route path="/threat-intelligence/iocs" element={<ProtectedRoute><IOCListView /></ProtectedRoute>} />
      <Route path="/threat-intelligence/iocs/:id" element={<ProtectedRoute><IOCDetailView /></ProtectedRoute>} />
      <Route path="/threat-intelligence/graph" element={<ProtectedRoute><IOCGraphView /></ProtectedRoute>} />
      <Route path="/threat-intelligence/watchlist" element={<ProtectedRoute><IOCWatchlistView /></ProtectedRoute>} />

      {/* Workspaces / Projects — vuln-lifecycle foundation (Task 1) */}
      <Route path="/workspaces/new" element={<ProtectedRoute><WorkspaceFormView /></ProtectedRoute>} />
      <Route path="/workspaces/:id/edit" element={<ProtectedRoute><WorkspaceFormView /></ProtectedRoute>} />
      <Route path="/workspaces/:id" element={<ProtectedRoute><WorkspaceDetailView /></ProtectedRoute>} />
      <Route path="/workspaces" element={<ProtectedRoute><WorkspaceListView /></ProtectedRoute>} />

      <Route path="/projects/new" element={<ProtectedRoute><ProjectFormView /></ProtectedRoute>} />
      <Route path="/projects/:id/edit" element={<ProtectedRoute><ProjectFormView /></ProtectedRoute>} />
      <Route path="/projects/:id" element={<ProtectedRoute><ProjectDetailView /></ProtectedRoute>} />
      <Route path="/projects" element={<ProtectedRoute><ProjectListView /></ProtectedRoute>} />

      {/* Findings — vuln-lifecycle Scan -> Finding pipeline (Task 2) */}
      <Route path="/projects/:id/findings/:findingId" element={<ProtectedRoute><FindingDetailView /></ProtectedRoute>} />
      <Route path="/projects/:id/findings" element={<ProtectedRoute><FindingListView /></ProtectedRoute>} />

      {/* My Tasks — vuln-lifecycle Assign + My Tasks (Task 4). Cross-project
          by design, visible to every authenticated user (not role-gated -
          anyone could be a developer-role assignee on some project). */}
      <Route path="/my-tasks" element={<ProtectedRoute><MyTasksView /></ProtectedRoute>} />

      {/* SLA Policies — vuln-lifecycle Fingerprinting + Rescan Diff + SLA (Task 3).
          Standalone for now - Task 7 wires this into the Admin Console's
          SLA/Policies tab nav. */}
      <Route path="/projects/:id/sla-policies" element={<ProtectedRoute><SlaPolicyView /></ProtectedRoute>} />

      {/* Assets — Phase 3 */}
      <Route path="/assets" element={<ProtectedRoute><AssetInventoryView /></ProtectedRoute>} />
      <Route path="/assets/:id" element={<ProtectedRoute><AssetProfileView /></ProtectedRoute>} />

      {/* Vulnerability Center — Phase 3 */}
      <Route path="/vulnerabilities/patches" element={<ProtectedRoute><PatchTrackingView /></ProtectedRoute>} />
      <Route path="/vulnerabilities/watchlist" element={
        <ProtectedRoute>
          <VulnerabilityListView watchlistOnly />
        </ProtectedRoute>
      } />
      <Route path="/vulnerabilities" element={<ProtectedRoute><VulnerabilityListView /></ProtectedRoute>} />
      <Route path="/vulnerabilities/:id" element={
        <ProtectedRoute>
          <VulnerabilityDetailView />
        </ProtectedRoute>
      } />

      {/* Attack Graph */}
      <Route path="/attack-graph" element={<ProtectedRoute><AttackGraphView /></ProtectedRoute>} />

      {/* MITRE */}
      <Route path="/mitre" element={<ProtectedRoute><MitreMatrixView /></ProtectedRoute>} />
      <Route path="/mitre/techniques/:id" element={<ProtectedRoute><MitreTechniqueDetailView /></ProtectedRoute>} />

      {/* Alerts */}
      <Route path="/alerts" element={<ProtectedRoute><AlertsView /></ProtectedRoute>} />
      <Route path="/alerts/:id" element={<ProtectedRoute><AlertDetailView /></ProtectedRoute>} />

      {/* Incidents */}
      <Route path="/incidents" element={<ProtectedRoute><IncidentListView /></ProtectedRoute>} />
      <Route path="/incidents/:id/playbook" element={<ProtectedRoute><IncidentPlaybookView /></ProtectedRoute>} />
      <Route path="/incidents/:id" element={<ProtectedRoute><IncidentDetailView /></ProtectedRoute>} />

      {/* News */}
      <Route path="/news" element={<ProtectedRoute><SecurityNewsView /></ProtectedRoute>} />
      <Route path="/news/:id" element={<ProtectedRoute><SecurityNewsDetailView /></ProtectedRoute>} />

      {/* Reports */}
      <Route path="/reports" element={<ProtectedRoute><ReportsCenterView /></ProtectedRoute>} />
      <Route path="/reports/builder" element={<ProtectedRoute><ReportBuilderView /></ProtectedRoute>} />
      <Route path="/reports/history" element={<ProtectedRoute><ReportHistoryView /></ProtectedRoute>} />

      {/* Administration (Guarded) - real, DB-backed RBAC management (Phase 3.1) */}
      <Route path="/admin/overview" element={<AdminRoute><AdminOverviewView /></AdminRoute>} />
      <Route path="/admin/health" element={<AdminRoute><AdminOverviewView /></AdminRoute>} />
      <Route path="/admin/users" element={<AdminRoute><UserManagementView /></AdminRoute>} />
      <Route path="/admin/audit" element={<AdminRoute><AdminAuditView /></AdminRoute>} />
      {/* Task 7: Admin Console Upgrade - vuln-lifecycle entity visibility. */}
      <Route path="/admin/workspaces" element={<AdminRoute><AdminWorkspacesView /></AdminRoute>} />
      <Route path="/admin/projects" element={<AdminRoute><AdminProjectsView /></AdminRoute>} />
      <Route path="/admin/findings" element={<AdminRoute><AdminFindingsView /></AdminRoute>} />
      <Route path="/admin/sla-policies" element={<AdminRoute><AdminSlaPoliciesView /></AdminRoute>} />
      <Route path="/admin/crawler" element={<AdminRoute><AdminOverviewView /></AdminRoute>} />
      <Route path="/admin/rag" element={<AdminRoute><AdminOverviewView /></AdminRoute>} />
      <Route path="/admin/settings" element={<AdminRoute><AdminOverviewView /></AdminRoute>} />

      {/* Not part of this build's demo scope - never linked from any menu.
          Redirected (not a hard 404) so an old bookmark/link still lands
          somewhere real instead of showing mock/placeholder content. */}
      <Route path="/admin/roles" element={<Navigate to="/admin/overview" replace />} />
      <Route path="/admin/permissions" element={<Navigate to="/admin/overview" replace />} />

      {/* Other System Screens */}
      <Route path="/profile" element={<ProtectedRoute><ProfileView /></ProtectedRoute>} />
      <Route path="/notifications" element={<ProtectedRoute><NotificationsView /></ProtectedRoute>} />
      <Route path="/onboarding" element={<ProtectedRoute><OnboardingView /></ProtectedRoute>} />
      <Route path="/500" element={<ProtectedRoute><ServerErrorView /></ProtectedRoute>} />

      {/* Fallback Redirection */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<ProtectedRoute><NotFoundView /></ProtectedRoute>} />

    </Routes>
  );
};
