import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, ArrowLeft, CheckCircle, Clock } from 'lucide-react';
import { listPatchTasks, setPatchTaskStatus, type PatchStatus, type PatchTask } from '../../../lib/api/vulnerabilities';

const COLUMNS: Array<{ key: PatchStatus; label: string; color: string; icon: React.ElementType }> = [
  { key: 'not_started', label: 'Chưa bắt đầu', color: 'border-t-critical', icon: AlertCircle },
  { key: 'in_progress', label: 'Đang xử lý', color: 'border-t-warning', icon: Clock },
  { key: 'patched', label: 'Đã vá', color: 'border-t-success', icon: CheckCircle },
];

export const PatchTrackingView: React.FC = () => {
  const [items, setItems] = useState<PatchTask[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const load = () => {
    setIsLoading(true);
    setError('');
    listPatchTasks()
      .then((page) => setItems(page.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải danh sách công việc vá lỗi.'))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);

  const move = async (task: PatchTask, status: PatchStatus) => {
    await setPatchTaskStatus(task.id, status);
    load();
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <Link to="/vulnerabilities" className="flex items-center gap-1.5 text-text-muted hover:text-primary text-xs font-mono mb-1.5">
            <ArrowLeft className="h-3.5 w-3.5" /> Lỗ hổng bảo mật
          </Link>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Bảng theo dõi vá lỗi</h2>
          <p className="text-xs text-text-secondary">Bảng Kanban theo dõi tiến độ khắc phục.</p>
        </div>
        <div className="text-right text-[10px] font-mono text-text-muted">
          <span className="block">{items.length} MỤC ĐANG HOẠT ĐỘNG</span>
          <span className="text-primary">DỮ LIỆU TỪ API</span>
        </div>
      </div>

      {error && <div className="rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical">{error}</div>}
      {isLoading ? <div className="py-12 text-center text-xs text-text-muted">Đang tải bảng theo dõi vá lỗi...</div> : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="patch-kanban-board">
          {COLUMNS.map((col) => {
            const Icon = col.icon;
            const colItems = items.filter((item) => item.status === col.key);
            return (
              <div key={col.key} className={`bg-surface-container border border-surface-container-highest rounded-lg overflow-hidden border-t-2 ${col.color}`}>
                <div className="flex items-center gap-2 px-4 py-3 border-b border-surface-container-highest bg-background/20">
                  <Icon className="h-4 w-4 text-primary" />
                  <span className="text-xs font-headline font-bold text-text-primary">{col.label}</span>
                  <span className="ml-auto text-[10px] font-mono text-text-muted">{colItems.length}</span>
                </div>
                <div className="p-3 space-y-2 min-h-[200px]">
                  {colItems.length === 0 ? <p className="py-8 text-center text-xs text-text-muted">Không có mục nào</p> : colItems.map((item) => (
                    <div key={item.id} className="bg-background/40 border border-surface-container-highest/60 rounded-lg p-3 space-y-2" data-testid={`patch-card-${item.id}`}>
                      <Link to={`/vulnerabilities/${item.vulnerability_id}`} className="text-xs font-mono font-black text-text-primary hover:text-primary">{item.cve_id}</Link>
                      <p className="text-[10px] text-text-muted leading-tight line-clamp-2">{item.title}</p>
                      <div className="bg-surface-container border border-surface-container-highest rounded px-2 py-1">
                        <span className="text-[9px] font-mono text-text-muted block uppercase tracking-widest">Tài sản</span>
                        <span className="text-[10px] font-mono text-text-primary font-bold">{item.asset_name || 'Chưa gắn tài sản'}</span>
                      </div>
                      <select value={item.status} onChange={(e) => move(item, e.target.value as PatchStatus)} className="w-full bg-background border border-surface-container-highest rounded px-2 py-1 text-[10px]">
                        <option value="not_started">Chưa bắt đầu</option>
                        <option value="in_progress">Đang xử lý</option>
                        <option value="patched">Đã vá</option>
                        <option value="accepted_risk">Chấp nhận rủi ro</option>
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default PatchTrackingView;
