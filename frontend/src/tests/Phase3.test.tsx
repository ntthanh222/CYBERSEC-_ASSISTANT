import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import React from 'react';

import { ThreatIntelView } from '../features/threat-intel/views/ThreatIntelView';
import { IOCListView } from '../features/threat-intel/views/IOCListView';
import { IOCDetailView } from '../features/threat-intel/views/IOCDetailView';
import { IOCGraphView } from '../features/threat-intel/views/IOCGraphView';
import { IOCWatchlistView } from '../features/threat-intel/views/IOCWatchlistView';
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
import { NotificationsView } from '../features/notifications/views/NotificationsView';

vi.mock('../lib/api/threatIntel', async () => {
  const actual = await vi.importActual<typeof import('../lib/api/threatIntel')>('../lib/api/threatIntel');
  return {
    ...actual,
    getThreatIntelSummary: vi.fn(),
    listThreatIOCs: vi.fn(),
    getThreatIOC: vi.fn(),
    createThreatIOC: vi.fn(),
    setThreatIOCWatchlist: vi.fn(),
  };
});

vi.mock('../lib/api/vulnerabilities', async () => {
  const actual = await vi.importActual<typeof import('../lib/api/vulnerabilities')>('../lib/api/vulnerabilities');
  return {
    ...actual,
    listVulnerabilities: vi.fn(),
    getVulnerability: vi.fn(),
    createVulnerability: vi.fn(),
    setVulnerabilityWatchlist: vi.fn(),
    listPatchTasks: vi.fn(),
    createPatchTask: vi.fn(),
    setPatchTaskStatus: vi.fn(),
  };
});

vi.mock('../lib/api/alerts', async () => {
  const actual = await vi.importActual<typeof import('../lib/api/alerts')>('../lib/api/alerts');
  return {
    ...actual,
    listAlerts: vi.fn(),
    createAlert: vi.fn(),
    getAlert: vi.fn(),
    setAlertStatus: vi.fn(),
  };
});

vi.mock('../lib/api/incidents', async () => {
  const actual = await vi.importActual<typeof import('../lib/api/incidents')>('../lib/api/incidents');
  return {
    ...actual,
    listIncidents: vi.fn(),
    createIncident: vi.fn(),
    getIncident: vi.fn(),
    setIncidentStatus: vi.fn(),
    createIncidentTask: vi.fn(),
    setIncidentTaskStatus: vi.fn(),
    addIncidentNote: vi.fn(),
  };
});

vi.mock('../lib/api/mitre', async () => {
  const actual = await vi.importActual<typeof import('../lib/api/mitre')>('../lib/api/mitre');
  return {
    ...actual,
    getMitreMatrix: vi.fn(),
    listMitreTechniques: vi.fn(),
    createMitreTechnique: vi.fn(),
    getMitreTechnique: vi.fn(),
    updateMitreTechnique: vi.fn(),
  };
});

vi.mock('../lib/api/attackGraph', async () => {
  const actual = await vi.importActual<typeof import('../lib/api/attackGraph')>('../lib/api/attackGraph');
  return {
    ...actual,
    getAttackGraph: vi.fn(),
    createAttackNode: vi.fn(),
    createAttackEdge: vi.fn(),
    generateAttackGraphFromIncident: vi.fn(),
  };
});

vi.mock('../lib/api/securityNews', async () => {
  const actual = await vi.importActual<typeof import('../lib/api/securityNews')>('../lib/api/securityNews');
  return {
    ...actual,
    listSecurityNews: vi.fn(),
    createSecurityNews: vi.fn(),
    getSecurityNews: vi.fn(),
    setSecurityNewsBookmark: vi.fn(),
    setSecurityNewsRead: vi.fn(),
  };
});

vi.mock('../lib/api/reports', async () => {
  const actual = await vi.importActual<typeof import('../lib/api/reports')>('../lib/api/reports');
  return {
    ...actual,
    listReportTemplates: vi.fn(),
    listReports: vi.fn(),
    createReport: vi.fn(),
    getReport: vi.fn(),
    downloadReportContent: vi.fn(),
  };
});

vi.mock('../lib/api/notifications', async () => {
  const actual = await vi.importActual<typeof import('../lib/api/notifications')>('../lib/api/notifications');
  return {
    ...actual,
    listNotifications: vi.fn(),
    setNotificationRead: vi.fn(),
  };
});

import {
  createThreatIOC,
  getThreatIntelSummary,
  getThreatIOC,
  listThreatIOCs,
  setThreatIOCWatchlist,
  type ThreatIOC,
} from '../lib/api/threatIntel';
import {
  createPatchTask,
  createVulnerability,
  getVulnerability,
  listPatchTasks,
  listVulnerabilities,
  setPatchTaskStatus,
  setVulnerabilityWatchlist,
  type PatchTask,
  type VulnerabilityRecord,
} from '../lib/api/vulnerabilities';
import {
  createAlert,
  getAlert,
  listAlerts,
  setAlertStatus,
  type AlertRecord,
} from '../lib/api/alerts';
import {
  addIncidentNote,
  createIncident,
  createIncidentTask,
  getIncident,
  listIncidents,
  setIncidentStatus,
  setIncidentTaskStatus,
  type IncidentDetail,
  type IncidentRecord,
  type IncidentTask,
  type IncidentTimelineEvent,
} from '../lib/api/incidents';
import {
  createMitreTechnique,
  getMitreMatrix,
  getMitreTechnique,
  listMitreTechniques,
  updateMitreTechnique,
  type MitreMatrix,
  type MitreTechnique,
} from '../lib/api/mitre';
import {
  createAttackEdge,
  createAttackNode,
  generateAttackGraphFromIncident,
  getAttackGraph,
  type AttackGraph,
  type AttackGraphEdge,
  type AttackGraphNode,
} from '../lib/api/attackGraph';
import {
  createSecurityNews,
  getSecurityNews,
  listSecurityNews,
  setSecurityNewsBookmark,
  setSecurityNewsRead,
  type SecurityNewsArticle,
} from '../lib/api/securityNews';
import {
  createReport,
  downloadReportContent,
  listReportTemplates,
  listReports,
  type ReportRecord,
  type ReportTemplate,
} from '../lib/api/reports';
import {
  listNotifications,
  setNotificationRead,
  type NotificationRecord,
} from '../lib/api/notifications';

const testIOC: ThreatIOC = {
  id: '11111111-1111-4111-8111-111111111111',
  type: 'domain',
  value: 'malware.example',
  severity: 'critical',
  confidence: 'high',
  description: 'Command and control domain observed by analyst.',
  source: 'Analyst import',
  first_seen: '2026-08-04T01:00:00Z',
  last_seen: '2026-08-04T02:00:00Z',
  watchlist: false,
  tags: ['c2'],
  mitre_techniques: ['T1071.001'],
  risk_timeline: [{ time: 'now', score: 95 }],
  created_at: '2026-08-04T02:00:00Z',
  updated_at: '2026-08-04T02:00:00Z',
};

const testVulnerability: VulnerabilityRecord = {
  id: '22222222-2222-4222-8222-222222222222',
  asset_id: null,
  cve_id: 'CVE-2026-10001',
  title: 'Example tracked vulnerability',
  description: 'Analyst-tracked vulnerability for remediation workflow.',
  cvss: 8.8,
  severity: 'high',
  published_date: '2026-08-04T03:00:00Z',
  updated_date: '2026-08-04T03:00:00Z',
  references: ['https://nvd.nist.gov/vuln/detail/CVE-2026-10001'],
  affected_products: ['Example Product'],
  remediation: 'Apply vendor patch.',
  watchlist: false,
  created_at: '2026-08-04T03:00:00Z',
  updated_at: '2026-08-04T03:00:00Z',
};

const testPatchTask: PatchTask = {
  id: '33333333-3333-4333-8333-333333333333',
  vulnerability_id: testVulnerability.id,
  cve_id: testVulnerability.cve_id,
  title: testVulnerability.title,
  cvss: testVulnerability.cvss,
  asset_id: null,
  asset_name: 'Finance Gateway',
  status: 'not_started',
  notes: '',
  created_at: '2026-08-04T03:10:00Z',
  updated_at: '2026-08-04T03:10:00Z',
};

const testAlert: AlertRecord = {
  id: '44444444-4444-4444-8444-444444444444',
  title: 'Suspicious outbound connection',
  description: 'Endpoint attempted outbound connection to a known bad host.',
  severity: 'high',
  source: 'EDR',
  status: 'new',
  asset_id: null,
  vulnerability_id: null,
  asset_name: 'Finance Laptop',
  ioc_value: 'malware.example',
  evidence: 'process=browser.exe dest=malware.example',
  created_at: '2026-08-04T04:00:00Z',
  updated_at: '2026-08-04T04:00:00Z',
};

const testIncident: IncidentRecord = {
  id: '55555555-5555-4555-8555-555555555555',
  title: 'Phishing infection containment',
  description: 'Endpoint contacted a suspicious domain after user click.',
  severity: 'medium',
  status: 'open',
  assignee: 'analyst@example.com',
  source_alert_id: null,
  asset_name: 'Finance Laptop',
  cve_id: '',
  closed_at: null,
  created_at: '2026-08-04T05:00:00Z',
  updated_at: '2026-08-04T05:00:00Z',
};

const testIncidentTask: IncidentTask = {
  id: '66666666-6666-4666-8666-666666666666',
  incident_id: testIncident.id,
  title: 'Block suspicious domain',
  description: '',
  status: 'pending',
  owner: 'analyst@example.com',
  created_at: '2026-08-04T05:05:00Z',
  updated_at: '2026-08-04T05:05:00Z',
};

const testTimelineEvent: IncidentTimelineEvent = {
  id: '77777777-7777-4777-8777-777777777777',
  incident_id: testIncident.id,
  event_type: 'created',
  message: 'Incident created with severity medium.',
  actor: 'analyst@example.com',
  created_at: '2026-08-04T05:00:00Z',
};

const testIncidentDetail: IncidentDetail = {
  ...testIncident,
  tasks: [testIncidentTask],
  timeline: [testTimelineEvent],
};

const testMitreTechnique: MitreTechnique = {
  id: '88888888-8888-4888-8888-888888888888',
  incident_id: null,
  technique_id: 'T1071.001',
  tactic: 'Command and Control',
  name: 'Web Protocols',
  description: 'Application layer protocol over web channels.',
  detection: 'Review proxy logs.',
  mitigation: 'Restrict egress.',
  coverage_status: 'partial',
  data_sources: ['Proxy logs'],
  created_at: '2026-08-04T06:00:00Z',
  updated_at: '2026-08-04T06:00:00Z',
};

const testMitreMatrix: MitreMatrix = {
  summary: {
    total: 1,
    covered: 0,
    partial: 1,
    planned: 0,
    gaps: 0,
  },
  tactics: {
    'Command and Control': [testMitreTechnique],
  },
};

const testAttackNodeA: AttackGraphNode = {
  id: '99999999-9999-4999-8999-999999999999',
  node_type: 'attacker',
  label: 'External Host',
  ip_address: '198.51.100.42',
  status: 'compromised',
  severity: 'critical',
  description: 'Observed source host.',
  cves: [],
  position_x: 120,
  position_y: 160,
  created_at: '2026-08-04T07:00:00Z',
  updated_at: '2026-08-04T07:00:00Z',
};

const testAttackNodeB: AttackGraphNode = {
  ...testAttackNodeA,
  id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  node_type: 'database',
  label: 'Finance DB',
  ip_address: '10.0.0.20',
  status: 'vulnerable',
  severity: 'high',
  position_x: 360,
  position_y: 220,
};

const testAttackEdge: AttackGraphEdge = {
  id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  source_node_id: testAttackNodeA.id,
  target_node_id: testAttackNodeB.id,
  label: 'Potential pivot',
  status: 'potential',
  created_at: '2026-08-04T07:05:00Z',
  updated_at: '2026-08-04T07:05:00Z',
};

const testAttackGraph: AttackGraph = {
  nodes: [testAttackNodeA, testAttackNodeB],
  edges: [testAttackEdge],
};

const testNewsArticle: SecurityNewsArticle = {
  id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  title: 'Vendor releases critical patch',
  summary: 'A vendor advisory describes a critical remotely exploitable issue.',
  ai_summary: '',
  url: 'https://example.com/advisory',
  source: 'Vendor Advisory',
  published_at: '2026-08-04T08:00:00Z',
  category: 'Threat Advisory',
  related_cves: ['CVE-2026-10001'],
  bookmarked: false,
  read: false,
  created_at: '2026-08-04T08:00:00Z',
  updated_at: '2026-08-04T08:00:00Z',
};

const testReport: ReportRecord = {
  id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  title: 'Weekly SOC Summary',
  category: 'executive',
  format: 'markdown',
  status: 'completed',
  sections: ['Executive Summary', 'Open Actions'],
  scope: 'Week 31 SOC review.',
  content: '# Weekly SOC Summary\n\n## Executive Summary\nReal saved report content.\n',
  error_message: '',
  created_at: '2026-08-04T09:00:00Z',
  updated_at: '2026-08-04T09:00:00Z',
};

const testReportTemplate: ReportTemplate = {
  id: 'executive-overview',
  title: 'SOC Executive Security Overview',
  description: 'High-level summary for leadership.',
  category: 'executive',
  sections: ['Executive Summary', 'Key Risks'],
};

const testNotification: NotificationRecord = {
  id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
  title: 'New critical alert',
  body: 'A critical severity alert was raised.',
  category: 'alert',
  severity: 'critical',
  is_read: false,
  source_ref: 'alert:1234',
  created_at: '2026-08-04T09:00:00Z',
  updated_at: '2026-08-04T09:00:00Z',
};

const renderWithRouter = (ui: React.ReactElement, route = '/') =>
  render(<MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>);

const renderWithRouterAndParam = (
  Component: React.ComponentType,
  routePattern: string,
  routePath: string,
) =>
  render(
    <MemoryRouter initialEntries={[routePath]}>
      <Routes>
        <Route path={routePattern} element={<Component />} />
      </Routes>
    </MemoryRouter>,
  );

describe('Threat Intelligence API-backed views', () => {
  beforeEach(() => {
    vi.mocked(getThreatIntelSummary).mockResolvedValue({
      total: 1,
      critical: 1,
      watchlist: 0,
      recent_48h: 1,
      items: [testIOC],
    });
    vi.mocked(listThreatIOCs).mockResolvedValue({
      items: [testIOC],
      total: 1,
      page: 1,
      page_size: 20,
    });
    vi.mocked(getThreatIOC).mockResolvedValue(testIOC);
    vi.mocked(createThreatIOC).mockResolvedValue(testIOC);
    vi.mocked(setThreatIOCWatchlist).mockResolvedValue({ ...testIOC, watchlist: true });
  });

  it('renders summary counts from the threat-intel API response', async () => {
    renderWithRouter(<ThreatIntelView />);
    expect(await screen.findByText('malware.example')).toBeInTheDocument();
    expect(screen.getByText('Tổng số IOC')).toBeInTheDocument();
    expect(screen.getAllByText('1').length).toBeGreaterThan(0);
    expect(getThreatIntelSummary).toHaveBeenCalledOnce();
  });

  it('creates an IOC through the API client and reloads the list', async () => {
    renderWithRouter(<IOCListView />);
    await screen.findByText('malware.example');
    fireEvent.change(screen.getByPlaceholderText('Giá trị IOC'), { target: { value: '203.0.113.10' } });
    fireEvent.change(screen.getByPlaceholderText('Nguồn'), { target: { value: 'Manual case note' } });
    fireEvent.click(screen.getByRole('button', { name: /Thêm IOC/i }));
    await waitFor(() => expect(createThreatIOC).toHaveBeenCalledWith(expect.objectContaining({
      value: '203.0.113.10',
      source: 'Manual case note',
    })));
    expect(listThreatIOCs).toHaveBeenCalled();
  });

  it('loads a detail record and persists watchlist changes through the API', async () => {
    renderWithRouterAndParam(IOCDetailView, '/threat-intelligence/iocs/:id', `/threat-intelligence/iocs/${testIOC.id}`);
    expect(await screen.findByText('malware.example')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /THÊM VÀO DANH SÁCH THEO DÕI/i }));
    await waitFor(() => expect(setThreatIOCWatchlist).toHaveBeenCalledWith(testIOC.id, true));
    expect(await screen.findByRole('button', { name: /ĐANG THEO DÕI/i })).toBeInTheDocument();
  });

  it('renders graph and watchlist from API data', async () => {
    vi.mocked(listThreatIOCs).mockResolvedValueOnce({ items: [testIOC], total: 1, page: 1, page_size: 40 });
    renderWithRouter(<IOCGraphView />);
    expect(await screen.findByTestId(`graph-node-${testIOC.id}`)).toBeInTheDocument();

    vi.mocked(listThreatIOCs).mockResolvedValueOnce({ items: [{ ...testIOC, watchlist: true }], total: 1, page: 1, page_size: 100 });
    renderWithRouter(<IOCWatchlistView />);
    expect(await screen.findByText('malware.example')).toBeInTheDocument();
  });
});

describe('Vulnerability API-backed views', () => {
  beforeEach(() => {
    vi.mocked(listVulnerabilities).mockResolvedValue({
      items: [testVulnerability],
      total: 1,
      page: 1,
      page_size: 50,
    });
    vi.mocked(getVulnerability).mockResolvedValue(testVulnerability);
    vi.mocked(createVulnerability).mockResolvedValue(testVulnerability);
    vi.mocked(setVulnerabilityWatchlist).mockResolvedValue({ ...testVulnerability, watchlist: true });
    vi.mocked(listPatchTasks).mockResolvedValue({
      items: [testPatchTask],
      total: 1,
      page: 1,
      page_size: 100,
    });
    vi.mocked(createPatchTask).mockResolvedValue(testPatchTask);
    vi.mocked(setPatchTaskStatus).mockResolvedValue({ status: 'updated' });
  });

  it('renders vulnerability cards from API data', async () => {
    renderWithRouter(<VulnerabilityListView />);
    expect(await screen.findByTestId(`vuln-card-${testVulnerability.id}`)).toBeInTheDocument();
    expect(screen.getByText('CVE-2026-10001')).toBeInTheDocument();
  });

  it('creates a tracked CVE through the API client', async () => {
    renderWithRouter(<VulnerabilityListView />);
    await screen.findByText('CVE-2026-10001');
    fireEvent.change(screen.getByPlaceholderText('CVE-2026-0001'), { target: { value: 'CVE-2026-20002' } });
    fireEvent.change(screen.getByPlaceholderText('Tiêu đề khuyến cáo'), { target: { value: 'New advisory' } });
    fireEvent.click(screen.getByRole('button', { name: /Thêm CVE/i }));
    await waitFor(() => expect(createVulnerability).toHaveBeenCalledWith(expect.objectContaining({
      cve_id: 'CVE-2026-20002',
      title: 'New advisory',
    })));
  });

  it('loads detail, updates watchlist, and creates patch task via API', async () => {
    renderWithRouterAndParam(VulnerabilityDetailView, '/vulnerabilities/:id', `/vulnerabilities/${testVulnerability.id}`);
    expect(await screen.findByText('Example tracked vulnerability')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /THÊM VÀO DANH SÁCH THEO DÕI/i }));
    await waitFor(() => expect(setVulnerabilityWatchlist).toHaveBeenCalledWith(testVulnerability.id, true));
    fireEvent.change(screen.getByPlaceholderText('Tên tài sản'), { target: { value: 'Finance Gateway' } });
    fireEvent.click(screen.getByRole('button', { name: /Thêm công việc/i }));
    await waitFor(() => expect(createPatchTask).toHaveBeenCalledWith(expect.objectContaining({
      vulnerability_id: testVulnerability.id,
      asset_name: 'Finance Gateway',
    })));
  });

  it('renders and updates patch tracking cards from API data', async () => {
    renderWithRouter(<PatchTrackingView />);
    expect(await screen.findByTestId(`patch-card-${testPatchTask.id}`)).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue('Chưa bắt đầu'), { target: { value: 'patched' } });
    await waitFor(() => expect(setPatchTaskStatus).toHaveBeenCalledWith(testPatchTask.id, 'patched'));
  });
});

describe('Alerts API-backed views', () => {
  beforeEach(() => {
    vi.mocked(listAlerts).mockResolvedValue({
      items: [testAlert],
      total: 1,
      page: 1,
      page_size: 100,
    });
    vi.mocked(createAlert).mockResolvedValue(testAlert);
    vi.mocked(getAlert).mockResolvedValue(testAlert);
    vi.mocked(setAlertStatus).mockResolvedValue({ ...testAlert, status: 'investigating' });
  });

  it('renders alert queue from API data and creates alerts through the client', async () => {
    renderWithRouter(<AlertsView />);
    expect(await screen.findByTestId(`alert-row-${testAlert.id}`)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('Tiêu đề cảnh báo'), { target: { value: 'New alert' } });
    fireEvent.change(screen.getByPlaceholderText('Nguồn'), { target: { value: 'SIEM' } });
    fireEvent.click(screen.getByRole('button', { name: /Thêm cảnh báo/i }));
    await waitFor(() => expect(createAlert).toHaveBeenCalledWith(expect.objectContaining({
      title: 'New alert',
      source: 'SIEM',
    })));
  });

  it('loads alert detail and persists status updates through API', async () => {
    renderWithRouterAndParam(AlertDetailView, '/alerts/:id', `/alerts/${testAlert.id}`);
    expect(await screen.findByText('Suspicious outbound connection')).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue('Mới'), { target: { value: 'investigating' } });
    await waitFor(() => expect(setAlertStatus).toHaveBeenCalledWith(testAlert.id, 'investigating'));
  });
});

describe('Incidents API-backed views', () => {
  beforeEach(() => {
    vi.mocked(listIncidents).mockResolvedValue({
      items: [testIncident],
      total: 1,
      page: 1,
      page_size: 100,
    });
    vi.mocked(createIncident).mockResolvedValue(testIncident);
    vi.mocked(getIncident).mockResolvedValue(testIncidentDetail);
    vi.mocked(setIncidentStatus).mockResolvedValue({ ...testIncident, status: 'contained' });
    vi.mocked(createIncidentTask).mockResolvedValue(testIncidentTask);
    vi.mocked(setIncidentTaskStatus).mockResolvedValue({ ...testIncidentTask, status: 'completed' });
    vi.mocked(addIncidentNote).mockResolvedValue({ ...testTimelineEvent, event_type: 'note', message: 'Host isolated.' });
    vi.mocked(listMitreTechniques).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
    vi.mocked(generateAttackGraphFromIncident).mockResolvedValue({ nodes: [], edges: [] });
  });

  it('renders incident queue from API data and creates incidents through the client', async () => {
    renderWithRouter(<IncidentListView />);
    expect(await screen.findByTestId(`incident-row-${testIncident.id}`)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('Tiêu đề sự cố'), { target: { value: 'New incident' } });
    fireEvent.click(screen.getByRole('button', { name: /Tạo sự cố/i }));
    await waitFor(() => expect(createIncident).toHaveBeenCalledWith(expect.objectContaining({
      title: 'New incident',
      severity: 'high',
    })));
  });

  it('loads incident detail and persists task, note, and status changes through API', async () => {
    renderWithRouterAndParam(IncidentDetailView, '/incidents/:id', `/incidents/${testIncident.id}`);
    expect(await screen.findByText('Phishing infection containment')).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue('Mở'), { target: { value: 'contained' } });
    await waitFor(() => expect(setIncidentStatus).toHaveBeenCalledWith(testIncident.id, 'contained'));
    fireEvent.change(screen.getByPlaceholderText('Tiêu đề nhiệm vụ'), { target: { value: 'Collect logs' } });
    fireEvent.click(screen.getByRole('button', { name: /Thêm nhiệm vụ/i }));
    await waitFor(() => expect(createIncidentTask).toHaveBeenCalledWith(testIncident.id, expect.objectContaining({
      title: 'Collect logs',
    })));
    fireEvent.change(screen.getByPlaceholderText('Thêm ghi chú vào dòng thời gian'), { target: { value: 'Host isolated.' } });
    fireEvent.click(screen.getByRole('button', { name: /Thêm ghi chú/i }));
    await waitFor(() => expect(addIncidentNote).toHaveBeenCalledWith(testIncident.id, 'Host isolated.'));
  });

  it('runs playbook steps from real incident tasks', async () => {
    renderWithRouterAndParam(IncidentPlaybookView, '/incidents/:id/playbook', `/incidents/${testIncident.id}/playbook`);
    expect(await screen.findByTestId(`playbook-step-${testIncidentTask.id}`)).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue('Chờ xử lý'), { target: { value: 'completed' } });
    await waitFor(() => expect(setIncidentTaskStatus).toHaveBeenCalledWith(testIncidentTask.id, 'completed'));
  });
});

describe('MITRE API-backed views', () => {
  beforeEach(() => {
    vi.mocked(getMitreMatrix).mockResolvedValue(testMitreMatrix);
    vi.mocked(createMitreTechnique).mockResolvedValue(testMitreTechnique);
    vi.mocked(getMitreTechnique).mockResolvedValue(testMitreTechnique);
    vi.mocked(updateMitreTechnique).mockResolvedValue({
      ...testMitreTechnique,
      coverage_status: 'covered',
    });
  });

  it('renders matrix records from API data and creates coverage through the client', async () => {
    renderWithRouter(<MitreMatrixView />);
    expect(await screen.findByTestId(`mitre-technique-${testMitreTechnique.id}`)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('T1071.001'), { target: { value: 'T1059' } });
    fireEvent.change(screen.getByPlaceholderText('Command and Control'), { target: { value: 'Execution' } });
    fireEvent.change(screen.getByPlaceholderText('Tên kỹ thuật'), { target: { value: 'Command Shell' } });
    fireEvent.click(screen.getByRole('button', { name: /Thêm Kỹ thuật/i }));
    await waitFor(() => expect(createMitreTechnique).toHaveBeenCalledWith(expect.objectContaining({
      technique_id: 'T1059',
      tactic: 'Execution',
      name: 'Command Shell',
    })));
  });

  it('loads technique detail and persists coverage updates through API', async () => {
    renderWithRouterAndParam(MitreTechniqueDetailView, '/mitre/techniques/:id', `/mitre/techniques/${testMitreTechnique.id}`);
    expect(await screen.findByText('Web Protocols')).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue('Một phần'), { target: { value: 'covered' } });
    fireEvent.click(screen.getByRole('button', { name: /Lưu Bao phủ/i }));
    await waitFor(() => expect(updateMitreTechnique).toHaveBeenCalledWith(testMitreTechnique.id, expect.objectContaining({
      coverage_status: 'covered',
    })));
  });
});

describe('Attack Graph API-backed view', () => {
  beforeEach(() => {
    vi.mocked(getAttackGraph).mockResolvedValue(testAttackGraph);
    vi.mocked(createAttackNode).mockResolvedValue(testAttackNodeA);
    vi.mocked(createAttackEdge).mockResolvedValue(testAttackEdge);
  });

  it('renders graph nodes and edges from API data', async () => {
    renderWithRouter(<AttackGraphView />);
    expect(await screen.findByTestId('attack-graph-canvas')).toBeInTheDocument();
    expect(screen.getByTestId(`attack-node-${testAttackNodeA.id}`)).toBeInTheDocument();
    expect(screen.getByTestId(`attack-edge-${testAttackEdge.id}`)).toBeInTheDocument();
  });

  it('creates graph nodes and edges through the API client', async () => {
    renderWithRouter(<AttackGraphView />);
    await screen.findByTestId('attack-graph-canvas');
    fireEvent.change(screen.getByPlaceholderText('Tên node'), { target: { value: 'New Node' } });
    fireEvent.click(screen.getByRole('button', { name: /Node/i }));
    await waitFor(() => expect(createAttackNode).toHaveBeenCalledWith(expect.objectContaining({
      label: 'New Node',
      node_type: 'asset',
    })));

    fireEvent.change(screen.getByDisplayValue('Nguồn'), { target: { value: testAttackNodeA.id } });
    fireEvent.change(screen.getByDisplayValue('Mục tiêu'), { target: { value: testAttackNodeB.id } });
    fireEvent.change(screen.getByPlaceholderText('Tên đường liên kết'), { target: { value: 'New path' } });
    fireEvent.click(screen.getByRole('button', { name: /Thêm liên kết/i }));
    await waitFor(() => expect(createAttackEdge).toHaveBeenCalledWith(expect.objectContaining({
      source_node_id: testAttackNodeA.id,
      target_node_id: testAttackNodeB.id,
      label: 'New path',
    })));
  });
});

describe('Security News API-backed views', () => {
  beforeEach(() => {
    vi.mocked(listSecurityNews).mockResolvedValue({
      items: [testNewsArticle],
      total: 1,
      page: 1,
      page_size: 100,
    });
    vi.mocked(createSecurityNews).mockResolvedValue(testNewsArticle);
    vi.mocked(getSecurityNews).mockResolvedValue(testNewsArticle);
    vi.mocked(setSecurityNewsBookmark).mockResolvedValue({ ...testNewsArticle, bookmarked: true });
    vi.mocked(setSecurityNewsRead).mockResolvedValue({ ...testNewsArticle, read: true });
  });

  it('renders a read-first feed from API data with no manual-create form', async () => {
    renderWithRouter(<SecurityNewsView />);
    expect(await screen.findByTestId(`news-card-${testNewsArticle.id}`)).toBeInTheDocument();
    // The manual-create form moved to Control Console -> Crawler (admin-only)
    // - a normal user's News page must never render it.
    expect(screen.queryByPlaceholderText('Tiêu đề bài viết')).not.toBeInTheDocument();
    expect(createSecurityNews).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Đánh dấu' }));
    await waitFor(() => expect(setSecurityNewsBookmark).toHaveBeenCalledWith(testNewsArticle.id, true));
  });

  it('loads article detail and persists read/bookmark updates through API', async () => {
    renderWithRouterAndParam(SecurityNewsDetailView, '/news/:id', `/news/${testNewsArticle.id}`);
    expect(await screen.findByText('Vendor releases critical patch')).toBeInTheDocument();
    await waitFor(() => expect(setSecurityNewsRead).toHaveBeenCalledWith(testNewsArticle.id, true));
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(setSecurityNewsBookmark).toHaveBeenCalledWith(testNewsArticle.id, true));
  });
});

describe('Reports API-backed views', () => {
  beforeEach(() => {
    vi.mocked(listReportTemplates).mockResolvedValue([testReportTemplate]);
    vi.mocked(listReports).mockResolvedValue({
      items: [testReport],
      total: 1,
      page: 1,
      page_size: 100,
    });
    vi.mocked(createReport).mockResolvedValue(testReport);
    vi.mocked(downloadReportContent).mockResolvedValue(testReport.content);
  });

  it('renders generated reports and downloads real backend content', async () => {
    renderWithRouter(<ReportsCenterView />);
    expect(await screen.findByTestId(`report-row-${testReport.id}`)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Tải xuống/i }));
    await waitFor(() => expect(downloadReportContent).toHaveBeenCalledWith(testReport.id));
    expect(await screen.findByTestId('report-download-preview')).toHaveTextContent('Weekly SOC Summary');
  });

  it('loads templates and creates persisted reports through the client', async () => {
    renderWithRouter(<ReportBuilderView />);
    expect(await screen.findByTestId(`report-template-${testReportTemplate.id}`)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId(`report-template-${testReportTemplate.id}`));
    fireEvent.click(screen.getByRole('button', { name: /Tạo báo cáo/i }));
    await waitFor(() => expect(createReport).toHaveBeenCalledWith(expect.objectContaining({
      title: testReportTemplate.title,
      category: 'executive',
      format: 'markdown',
    })));
  });

  it('renders report history from API data', async () => {
    renderWithRouter(<ReportHistoryView />, `/reports/history?report=${testReport.id}`);
    expect(await screen.findByTestId(`report-history-${testReport.id}`)).toBeInTheDocument();
    expect(screen.getByText(/Real saved report content/i)).toBeInTheDocument();
  });
});

describe('Notifications API-backed view', () => {
  beforeEach(() => {
    vi.mocked(listNotifications).mockResolvedValue({
      items: [testNotification],
      total: 1,
      page: 1,
      page_size: 100,
      unread_count: 1,
    });
    vi.mocked(setNotificationRead).mockResolvedValue({ ...testNotification, is_read: true });
  });

  it('renders real unread notifications and marks them read through the API', async () => {
    renderWithRouter(<NotificationsView />);
    expect(await screen.findByTestId(`notification-${testNotification.id}`)).toBeInTheDocument();
    expect(screen.getByText('New critical alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Mark read/i }));
    await waitFor(() =>
      expect(setNotificationRead).toHaveBeenCalledWith(testNotification.id, true)
    );
  });

  it('shows an honest empty state when there are no notifications', async () => {
    vi.mocked(listNotifications).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
      unread_count: 0,
    });
    renderWithRouter(<NotificationsView />);
    expect(await screen.findByText(/No notifications yet/i)).toBeInTheDocument();
  });
});
