import React, { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { listReports, type ReportRecord } from '../../../lib/api/reports';

export const ReportHistoryView: React.FC = () => {
  const location = useLocation();
  const [items, setItems] = useState<ReportRecord[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    listReports()
      .then((page) => setItems(page.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải lịch sử báo cáo.'));
  }, []);

  const selected = useMemo(() => {
    const reportId = new URLSearchParams(location.search).get('report');
    return items.find((item) => item.id === reportId);
  }, [items, location.search]);

  if (error) return <div className="py-12 text-center text-xs text-critical">{error}</div>;

  return (
    <div className="space-y-6">
      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Lịch sử Báo cáo</h2>
        <p className="text-xs text-text-secondary">Bản ghi tạo báo cáo đã được lưu trữ.</p>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="space-y-3">
          {items.length === 0 ? <div className="py-8 text-center text-xs text-text-muted border border-dashed border-surface-container-highest rounded-lg">Chưa có lịch sử báo cáo.</div> : items.map((report) => (
            <article key={report.id} className="bg-surface-container border border-surface-container-highest rounded-lg p-3" data-testid={`report-history-${report.id}`}>
              <p className="text-sm font-bold text-text-primary">{report.title}</p>
              <p className="text-[10px] text-text-muted">{report.status} - {report.format}</p>
            </article>
          ))}
        </section>
        <section className="xl:col-span-2 bg-surface-container border border-surface-container-highest rounded-lg p-4">
          {selected ? (
            <pre className="text-xs whitespace-pre-wrap text-text-secondary">{selected.content}</pre>
          ) : (
            <p className="text-xs text-text-muted">Chọn một báo cáo từ Reports Center để xem trước nội dung.</p>
          )}
        </section>
      </div>
    </div>
  );
};

export default ReportHistoryView;
