import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, CircleDot, ListChecks } from 'lucide-react';
import {
  createIncidentTask,
  getIncident,
  setIncidentTaskStatus,
  type IncidentDetail,
  type IncidentTaskStatus,
} from '../../../lib/api/incidents';

const STATUS_OPTIONS: IncidentTaskStatus[] = ['pending', 'in_progress', 'completed', 'blocked'];
const STATUS_LABELS: Record<IncidentTaskStatus, string> = {
  pending: 'Chờ xử lý',
  in_progress: 'Đang xử lý',
  completed: 'Hoàn thành',
  blocked: 'Bị chặn',
};

export const IncidentPlaybookView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState('');
  const [step, setStep] = useState('');

  const load = () => {
    if (!id) return;
    setError('');
    getIncident(id)
      .then(setIncident)
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải kịch bản xử lý.'));
  };

  useEffect(load, [id]);

  const addStep = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!incident) return;
    await createIncidentTask(incident.id, { title: step, status: 'pending' });
    setStep('');
    load();
  };

  const updateStep = async (taskId: string, status: IncidentTaskStatus) => {
    await setIncidentTaskStatus(taskId, status);
    load();
  };

  if (error) return <div className="py-20 text-center text-xs text-critical">{error}</div>;
  if (!incident) return <div className="py-20 text-center text-xs text-text-muted">Đang tải kịch bản xử lý...</div>;

  const complete = incident.tasks.filter((task) => task.status === 'completed').length;

  return (
    <div className="space-y-6">
      <Link to={`/incidents/${incident.id}`} className="flex items-center gap-1.5 text-text-muted hover:text-primary text-xs font-mono">
        <ArrowLeft className="h-3.5 w-3.5" /> Quay lại Sự cố
      </Link>
      <div className="flex items-center justify-between border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Bảng điều khiển Kịch bản Xử lý</h2>
          <p className="text-xs text-text-secondary">{incident.title}</p>
        </div>
        <div className="text-xs font-mono text-text-muted">{complete}/{incident.tasks.length} HOÀN THÀNH</div>
      </div>

      <form onSubmit={addStep} className="flex gap-2 bg-surface-container border border-surface-container-highest rounded-lg p-3">
        <input required value={step} onChange={(e) => setStep(e.target.value)} placeholder="Thêm bước kịch bản" className="flex-1 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <button className="bg-primary text-background rounded px-3 py-2 text-xs font-bold">Thêm bước</button>
      </form>

      {incident.tasks.length === 0 ? (
        <div className="py-12 text-center text-xs text-text-muted border border-dashed border-surface-container-highest rounded-lg">Chưa có bước kịch bản nào được thêm vào sự cố này.</div>
      ) : (
        <div className="space-y-3">
          {incident.tasks.map((task, index) => (
            <div key={task.id} className="flex items-center gap-4 bg-surface-container border border-surface-container-highest rounded-lg p-4" data-testid={`playbook-step-${task.id}`}>
              {task.status === 'completed' ? <CheckCircle2 className="h-5 w-5 text-success" /> : <CircleDot className="h-5 w-5 text-primary" />}
              <div className="flex-1 min-w-0">
                <p className="text-[10px] text-text-muted font-mono">BƯỚC {index + 1}</p>
                <p className="text-sm font-bold text-text-primary">{task.title}</p>
              </div>
              <ListChecks className="h-4 w-4 text-text-muted" />
              <select value={task.status} onChange={(e) => updateStep(task.id, e.target.value as IncidentTaskStatus)} className="bg-background border border-surface-container-highest rounded px-2 py-1.5 text-xs">
                {STATUS_OPTIONS.map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}
              </select>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default IncidentPlaybookView;
