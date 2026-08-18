import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, ClipboardCheck, Crosshair, ShieldQuestion } from 'lucide-react';
import {
  addIncidentNote,
  createIncidentTask,
  getIncident,
  setIncidentStatus,
  setIncidentTaskStatus,
  type IncidentDetail,
  type IncidentStatus,
  type IncidentTaskStatus,
} from '../../../lib/api/incidents';
import {
  createMitreTechnique,
  linkMitreTechniqueToIncident,
  listMitreTechniques,
  type MitreTechnique,
} from '../../../lib/api/mitre';
import { generateAttackGraphFromIncident } from '../../../lib/api/attackGraph';

const TASK_STATUSES: IncidentTaskStatus[] = ['pending', 'in_progress', 'completed', 'blocked'];

const SEVERITY_LABELS: Record<string, string> = {
  critical: 'Nghiêm trọng',
  high: 'Cao',
  medium: 'Trung bình',
  low: 'Thấp',
};

export const IncidentDetailView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [taskTitle, setTaskTitle] = useState('');
  const [note, setNote] = useState('');
  const [techniques, setTechniques] = useState<MitreTechnique[]>([]);
  const [techniqueForm, setTechniqueForm] = useState({ technique_id: '', tactic: '', name: '' });
  const [isGeneratingGraph, setIsGeneratingGraph] = useState(false);

  const load = () => {
    if (!id) return;
    setIsLoading(true);
    setError('');
    getIncident(id)
      .then(setIncident)
      .catch((err) => setError(err instanceof Error ? err.message : 'Không tìm thấy sự cố.'))
      .finally(() => setIsLoading(false));
  };

  const loadTechniques = useCallback(() => {
    if (!id) return;
    listMitreTechniques({ incident_id: id })
      .then((page) => setTechniques(page.items))
      .catch(() => setTechniques([]));
  }, [id]);

  useEffect(load, [id]);
  useEffect(loadTechniques, [loadTechniques]);

  const linkTechnique = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!id) return;
    setError('');
    try {
      // A technique_id already tracked under this account (e.g. from a
      // prior incident) cannot be created again - the coverage table is
      // unique per (account, technique). Re-link the existing row to this
      // incident instead of failing with a raw conflict.
      const existing = await listMitreTechniques({ search: techniqueForm.technique_id });
      const match = existing.items.find(
        (item) => item.technique_id.toUpperCase() === techniqueForm.technique_id.toUpperCase(),
      );
      if (match) {
        await linkMitreTechniqueToIncident(match, id);
      } else {
        await createMitreTechnique({
          incident_id: id,
          technique_id: techniqueForm.technique_id,
          tactic: techniqueForm.tactic,
          name: techniqueForm.name,
          coverage_status: 'gap',
        });
      }
      setTechniqueForm({ technique_id: '', tactic: '', name: '' });
      loadTechniques();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể liên kết kỹ thuật MITRE.');
    }
  };

  const generateGraph = async () => {
    if (!incident) return;
    setError('');
    setIsGeneratingGraph(true);
    try {
      await generateAttackGraphFromIncident(incident.id);
      navigate('/attack-graph');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể tạo Attack Graph.');
    } finally {
      setIsGeneratingGraph(false);
    }
  };

  const updateStatus = async (status: IncidentStatus) => {
    if (!incident) return;
    const updated = await setIncidentStatus(incident.id, status);
    setIncident({ ...incident, ...updated });
    load();
  };

  const addTask = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!incident) return;
    await createIncidentTask(incident.id, { title: taskTitle });
    setTaskTitle('');
    load();
  };

  const updateTask = async (taskId: string, status: IncidentTaskStatus) => {
    await setIncidentTaskStatus(taskId, status);
    load();
  };

  const submitNote = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!incident) return;
    await addIncidentNote(incident.id, note);
    setNote('');
    load();
  };

  if (isLoading) return <div className="py-20 text-center text-xs text-text-muted">Đang tải sự cố...</div>;
  if (!incident) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-lg">
        <AlertTriangle className="h-10 w-10 opacity-40 text-critical" />
        <p className="text-xs">{error || 'Không tìm thấy sự cố.'}</p>
        <Link to="/incidents" className="text-primary text-xs hover:underline">Quay lại danh sách sự cố</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link to="/incidents" className="flex items-center gap-1.5 text-text-muted hover:text-primary text-xs font-mono">
        <ArrowLeft className="h-3.5 w-3.5" /> Quay lại danh sách sự cố
      </Link>
      <div className="bg-surface-container border border-surface-container-highest rounded-lg p-6 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-headline font-black text-2xl text-text-primary">{incident.title}</h2>
            <p className="text-xs text-text-muted mt-1">{incident.asset_name || 'Chưa có tài sản'} - {new Date(incident.created_at).toLocaleString()}</p>
          </div>
          <select value={incident.status} onChange={(e) => updateStatus(e.target.value as IncidentStatus)} className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
            <option value="open">Mở</option>
            <option value="triaged">Đã phân loại</option>
            <option value="in_progress">Đang xử lý</option>
            <option value="contained">Đã kiểm soát</option>
            <option value="eradicated">Đã loại bỏ</option>
            <option value="recovered">Đã khôi phục</option>
            <option value="closed">Đã đóng</option>
          </select>
        </div>
        <p className="text-sm text-text-secondary leading-relaxed">{incident.description}</p>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
          <div className="bg-background border border-surface-container-highest rounded p-3">Mức độ nghiêm trọng: {SEVERITY_LABELS[incident.severity] ?? incident.severity}</div>
          <div className="bg-background border border-surface-container-highest rounded p-3">Người phụ trách: {incident.assignee || 'Chưa phân công'}</div>
          <div className="bg-background border border-surface-container-highest rounded p-3">CVE: {incident.cve_id || 'Không có'}</div>
          <Link to={`/incidents/${incident.id}/playbook`} className="bg-background border border-primary/30 rounded p-3 text-primary">Mở Playbook</Link>
        </div>
        <button
          onClick={generateGraph}
          disabled={isGeneratingGraph}
          data-testid="generate-attack-graph"
          className="flex items-center gap-1.5 bg-primary text-background rounded px-3 py-2 text-xs font-bold disabled:opacity-50"
        >
          <Crosshair className="h-3.5 w-3.5" /> {isGeneratingGraph ? 'Đang tạo Attack Graph...' : 'Tạo Attack Graph'}
        </button>
      </div>

      <section className="space-y-3">
        <h3 className="text-xs font-mono uppercase text-text-muted font-bold">Kỹ thuật MITRE</h3>
        <form onSubmit={linkTechnique} className="grid grid-cols-1 md:grid-cols-4 gap-2 rounded-lg border border-surface-container-highest bg-surface-container p-3">
          <input required value={techniqueForm.technique_id} onChange={(e) => setTechniqueForm({ ...techniqueForm, technique_id: e.target.value })} placeholder="Mã kỹ thuật (VD: T1078)" className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
          <input required value={techniqueForm.tactic} onChange={(e) => setTechniqueForm({ ...techniqueForm, tactic: e.target.value })} placeholder="Chiến thuật" className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
          <input required value={techniqueForm.name} onChange={(e) => setTechniqueForm({ ...techniqueForm, name: e.target.value })} placeholder="Tên kỹ thuật" className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
          <button className="bg-primary text-background rounded px-3 py-2 text-xs font-bold">Liên kết kỹ thuật</button>
        </form>
        {techniques.length === 0 ? (
          <div className="py-6 text-center text-xs text-text-muted border border-dashed border-surface-container-highest rounded-lg">Chưa có kỹ thuật MITRE nào được liên kết với sự cố này.</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {techniques.map((technique) => (
              <div key={technique.id} className="flex items-center gap-3 bg-surface-container border border-surface-container-highest rounded-lg p-3" data-testid={`incident-technique-${technique.id}`}>
                <ShieldQuestion className="h-4 w-4 text-primary shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-bold text-text-primary truncate">{technique.technique_id}: {technique.name}</p>
                  <p className="text-[10px] text-text-muted">{technique.tactic}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section className="space-y-3">
          <h3 className="text-xs font-mono uppercase text-text-muted font-bold">Nhiệm vụ xử lý</h3>
          <form onSubmit={addTask} className="flex gap-2">
            <input required value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} placeholder="Tiêu đề nhiệm vụ" className="flex-1 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
            <button className="bg-primary text-background rounded px-3 py-2 text-xs font-bold">Thêm nhiệm vụ</button>
          </form>
          {incident.tasks.length === 0 ? (
            <div className="py-8 text-center text-xs text-text-muted border border-dashed border-surface-container-highest rounded-lg">Chưa có nhiệm vụ xử lý nào.</div>
          ) : incident.tasks.map((task) => (
            <div key={task.id} className="flex items-center gap-3 bg-surface-container border border-surface-container-highest rounded-lg p-3" data-testid={`incident-task-${task.id}`}>
              <ClipboardCheck className="h-4 w-4 text-primary shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold text-text-primary truncate">{task.title}</p>
                <p className="text-[10px] text-text-muted">{task.owner || 'Chưa phân công'}</p>
              </div>
              <select value={task.status} onChange={(e) => updateTask(task.id, e.target.value as IncidentTaskStatus)} className="bg-background border border-surface-container-highest rounded px-2 py-1.5 text-xs">
                {TASK_STATUSES.map((status) => <option key={status} value={status}>{status.replace('_', ' ')}</option>)}
              </select>
            </div>
          ))}
        </section>

        <section className="space-y-3">
          <h3 className="text-xs font-mono uppercase text-text-muted font-bold">Dòng thời gian</h3>
          <form onSubmit={submitNote} className="flex gap-2">
            <input required value={note} onChange={(e) => setNote(e.target.value)} placeholder="Thêm ghi chú vào dòng thời gian" className="flex-1 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
            <button className="border border-surface-container-highest rounded px-3 py-2 text-xs font-bold">Thêm ghi chú</button>
          </form>
          {incident.timeline.map((event) => (
            <div key={event.id} className="bg-surface-container border border-surface-container-highest rounded-lg p-3">
              <p className="text-xs text-text-secondary">{event.message}</p>
              <p className="text-[10px] text-text-muted mt-1">{event.event_type} - {new Date(event.created_at).toLocaleString()}</p>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
};

export default IncidentDetailView;
