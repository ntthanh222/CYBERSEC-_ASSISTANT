import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft } from 'lucide-react';
import {
  getMitreTechnique,
  updateMitreTechnique,
  type CoverageStatus,
  type MitreTechnique,
} from '../../../lib/api/mitre';

export const MitreTechniqueDetailView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [technique, setTechnique] = useState<MitreTechnique | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    setError('');
    getMitreTechnique(id)
      .then(setTechnique)
      .catch((err) => setError(err instanceof Error ? err.message : 'Không tìm thấy kỹ thuật MITRE.'));
  }, [id]);

  const save = async () => {
    if (!technique) return;
    setTechnique(await updateMitreTechnique(technique.id, {
      detection: technique.detection,
      mitigation: technique.mitigation,
      coverage_status: technique.coverage_status,
      data_sources: technique.data_sources,
    }));
  };

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-lg">
        <AlertTriangle className="h-10 w-10 opacity-40 text-critical" />
        <p className="text-xs">{error}</p>
        <Link to="/mitre" className="text-primary text-xs hover:underline">Quay lại ma trận</Link>
      </div>
    );
  }
  if (!technique) return <div className="py-20 text-center text-xs text-text-muted">Đang tải kỹ thuật...</div>;

  return (
    <div className="space-y-6">
      <Link to="/mitre" className="flex items-center gap-1.5 text-text-muted hover:text-primary text-xs font-mono">
        <ArrowLeft className="h-3.5 w-3.5" /> Quay lại MITRE Matrix
      </Link>
      <div className="bg-surface-container border border-surface-container-highest rounded-lg p-6 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-primary text-xs">{technique.technique_id} - {technique.tactic}</p>
            <h2 className="font-headline font-black text-2xl text-text-primary">{technique.name}</h2>
          </div>
          <select value={technique.coverage_status} onChange={(e) => setTechnique({ ...technique, coverage_status: e.target.value as CoverageStatus })} className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
            <option value="planned">Đã lên kế hoạch</option>
            <option value="partial">Một phần</option>
            <option value="covered">Đã bao phủ</option>
            <option value="gap">Khoảng trống</option>
          </select>
        </div>
        <p className="text-sm text-text-secondary leading-relaxed">{technique.description || 'Chưa có mô tả được ghi nhận.'}</p>
        <label className="block space-y-2">
          <span className="text-[10px] font-mono text-text-muted uppercase font-bold">Phát hiện</span>
          <textarea value={technique.detection} onChange={(e) => setTechnique({ ...technique, detection: e.target.value })} className="w-full min-h-28 bg-background border border-surface-container-highest rounded p-3 text-xs" />
        </label>
        <label className="block space-y-2">
          <span className="text-[10px] font-mono text-text-muted uppercase font-bold">Giảm thiểu</span>
          <textarea value={technique.mitigation} onChange={(e) => setTechnique({ ...technique, mitigation: e.target.value })} className="w-full min-h-28 bg-background border border-surface-container-highest rounded p-3 text-xs" />
        </label>
        <button onClick={save} className="bg-primary text-background rounded px-4 py-2 text-xs font-bold">Lưu Bao phủ</button>
      </div>
    </div>
  );
};

export default MitreTechniqueDetailView;
