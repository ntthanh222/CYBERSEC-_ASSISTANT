import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, FileSpreadsheet, RefreshCw } from 'lucide-react';
import {
  createMitreTechnique,
  getMitreMatrix,
  type CoverageStatus,
  type MitreMatrix,
} from '../../../lib/api/mitre';

const STATUS_CHIP: Record<CoverageStatus, string> = {
  covered: 'bg-success/10 text-success border-success/20',
  partial: 'bg-warning/10 text-warning border-warning/20',
  planned: 'bg-primary/10 text-primary border-primary/20',
  gap: 'bg-critical/10 text-critical border-critical/20',
};

const STATUS_LABEL: Record<string, string> = {
  covered: 'ĐÃ BAO PHỦ',
  partial: 'MỘT PHẦN',
  planned: 'DỰ KIẾN',
  gap: 'THIẾU',
};

const SUMMARY_LABEL: Record<string, string> = {
  total: 'Tổng số',
  covered: 'Đã bao phủ',
  partial: 'Một phần',
  planned: 'Dự kiến',
  gaps: 'Còn thiếu',
};

export const MitreMatrixView: React.FC = () => {
  const [matrix, setMatrix] = useState<MitreMatrix | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [form, setForm] = useState({
    technique_id: '',
    tactic: '',
    name: '',
    coverage_status: 'planned' as CoverageStatus,
  });

  const load = useCallback(() => {
    setIsLoading(true);
    setError('');
    getMitreMatrix()
      .then(setMatrix)
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải dữ liệu bao phủ MITRE.'))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(load, [load]);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    try {
      await createMitreTechnique(form);
      setForm({ technique_id: '', tactic: '', name: '', coverage_status: 'planned' });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể thêm bao phủ kỹ thuật.');
    }
  };

  const summary = matrix?.summary ?? { total: 0, covered: 0, partial: 0, planned: 0, gaps: 0 };
  const tactics = matrix?.tactics ?? {};

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">MITRE ATT&CK Matrix</h2>
          <p className="text-xs text-text-secondary">Hồ sơ mức độ bao phủ do các nhà phân tích duy trì cho không gian làm việc này.</p>
        </div>
        <button onClick={load} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-surface-container-highest text-xs"><RefreshCw className="h-3.5 w-3.5" /> Làm mới</button>
      </div>

      <form onSubmit={handleCreate} className="grid grid-cols-1 lg:grid-cols-5 gap-2 rounded-lg border border-surface-container-highest bg-surface-container p-3">
        <input required value={form.technique_id} onChange={(e) => setForm({ ...form, technique_id: e.target.value })} placeholder="T1071.001" className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <input required value={form.tactic} onChange={(e) => setForm({ ...form, tactic: e.target.value })} placeholder="Command and Control" className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Tên kỹ thuật" className="lg:col-span-2 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <button className="bg-primary text-background rounded px-3 py-2 text-xs font-bold">Thêm Kỹ thuật</button>
      </form>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {Object.entries(summary).map(([key, value]) => (
          <div key={key} className="bg-surface-container border border-surface-container-highest rounded-lg p-3">
            <p className="text-[10px] uppercase font-mono text-text-muted">{SUMMARY_LABEL[key] ?? key}</p>
            <p className="text-xl font-black text-text-primary">{value}</p>
          </div>
        ))}
      </div>

      {error && <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical"><AlertTriangle className="h-4 w-4" />{error}</div>}

      {isLoading ? <div className="py-12 text-center text-xs text-text-muted">Đang tải ma trận MITRE...</div> : Object.keys(tactics).length === 0 ? (
        <div className="py-12 text-center text-xs text-text-muted border border-dashed border-surface-container-highest rounded-lg">Chưa có hồ sơ bao phủ MITRE nào được thêm.</div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          {Object.entries(tactics).map(([tactic, techniques]) => (
            <section key={tactic} className="space-y-3">
              <h3 className="text-xs font-mono uppercase text-text-muted font-bold">{tactic}</h3>
              {techniques.map((technique) => (
                <Link key={technique.id} to={`/mitre/techniques/${technique.id}`} className="block bg-surface-container border border-surface-container-highest rounded-lg p-3 hover:bg-surface-container-high/50" data-testid={`mitre-technique-${technique.id}`}>
                  <div className="flex items-center gap-2">
                    <FileSpreadsheet className="h-4 w-4 text-primary" />
                    <span className="font-mono text-xs text-primary">{technique.technique_id}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${STATUS_CHIP[technique.coverage_status]}`}>{STATUS_LABEL[technique.coverage_status] ?? technique.coverage_status.toUpperCase()}</span>
                  </div>
                  <p className="text-sm font-bold text-text-primary mt-2">{technique.name}</p>
                </Link>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
};

export default MitreMatrixView;
