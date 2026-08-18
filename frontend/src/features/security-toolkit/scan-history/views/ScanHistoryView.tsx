import React, { useState, useEffect, useCallback } from 'react';
import { ToolkitLayout } from '../../shared/ToolkitLayout';
import { listScanHistory, deleteScanHistoryRecord, getScanHistoryRecord } from '../../../../lib/api/scanHistory';
import type { ScanHistoryRecord } from '../../../../lib/api/scanHistory';
import { ApiError } from '../../../../lib/api/client';
import {
  Search, Trash2, ArrowUpDown, ChevronLeft, ChevronRight, AlertTriangle, Eye, X, Loader2
} from 'lucide-react';

const SCAN_TYPE_LABEL: Record<string, string> = {
  url_scan: 'Quét URL',
  cve_lookup: 'Tra cứu CVE',
};

const SEVERITY_LABEL: Record<string, string> = {
  critical: 'NGHIÊM TRỌNG',
  high: 'CAO',
  medium: 'TRUNG BÌNH',
  low: 'THẤP',
};

function ScanDetailsBody({ record }: { record: ScanHistoryRecord }) {
  const details = record.details;
  if (!details) {
    return <p className="text-text-muted italic text-xs">Không có phát hiện có cấu trúc nào được ghi nhận cho mục này.</p>;
  }
  if (record.scan_type === 'url_scan' && (Array.isArray(details.findings) || Array.isArray(details.recommendations))) {
    const findings = Array.isArray(details.findings) ? (details.findings as unknown[]) : [];
    const recommendations = Array.isArray(details.recommendations) ? (details.recommendations as unknown[]) : [];
    return (
      <div className="space-y-4">
        <div className="space-y-1.5">
          <span className="text-[9px] text-text-muted uppercase tracking-widest block font-bold">Phát hiện</span>
          {findings.length > 0 ? (
            <ul className="space-y-1 text-[11px] text-text-secondary">
              {findings.map((f, i) => {
                const message =
                  typeof f === 'string' ? f : (f as Record<string, unknown>)?.message;
                return (
                  <li key={i} className="flex items-start gap-1.5">
                    <span className="text-warning mt-0.5">•</span>
                    <span>{typeof message === 'string' ? message : JSON.stringify(f)}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-text-muted italic text-[11px]">Không có phát hiện nào.</p>
          )}
        </div>
        <div className="space-y-1.5">
          <span className="text-[9px] text-text-muted uppercase tracking-widest block font-bold">Khuyến nghị</span>
          {recommendations.length > 0 ? (
            <ul className="space-y-1 text-[11px] text-text-secondary">
              {recommendations.map((r, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className="text-primary mt-0.5">•</span>
                  <span>{typeof r === 'string' ? r : JSON.stringify(r)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-text-muted italic text-[11px]">Không có khuyến nghị nào được ghi nhận.</p>
          )}
        </div>
      </div>
    );
  }
  if (record.scan_type === 'cve_lookup' && ('source' in details || 'cached' in details)) {
    return (
      <dl className="space-y-2 text-[11px]">
        <div className="flex justify-between gap-4">
          <dt className="text-text-muted uppercase tracking-widest font-bold">Nguồn</dt>
          <dd className="text-text-secondary">{String(details.source ?? 'unknown')}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-text-muted uppercase tracking-widest font-bold">Lấy từ bộ nhớ đệm</dt>
          <dd className="text-text-secondary">{details.cached ? 'Có' : 'Không'}</dd>
        </div>
      </dl>
    );
  }
  return (
    <pre className="text-[10px] text-text-secondary whitespace-pre-wrap break-words bg-background/40 rounded-lg p-3 border border-surface-container-highest">
      {JSON.stringify(details, null, 2)}
    </pre>
  );
}

const PAGE_SIZE = 10;

export const ScanHistoryView: React.FC = () => {
  const [items, setItems] = useState<ScanHistoryRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'url_scan' | 'cve_lookup'>('all');
  const [severityFilter, setSeverityFilter] = useState<'all' | 'low' | 'medium' | 'high' | 'critical'>('all');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [currentPage, setCurrentPage] = useState(1);

  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [detailTargetId, setDetailTargetId] = useState<string | null>(null);
  const [detailRecord, setDetailRecord] = useState<ScanHistoryRecord | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const fetchHistory = useCallback(() => {
    setIsLoading(true);
    listScanHistory({
      page: currentPage,
      pageSize: PAGE_SIZE,
      scanType: typeFilter === 'all' ? undefined : typeFilter,
      severity: severityFilter === 'all' ? undefined : severityFilter,
      sort: sortDirection,
    })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
        setErrorMsg(null);
      })
      .catch((err) => {
        setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải lịch sử quét.');
      })
      .finally(() => setIsLoading(false));
  }, [currentPage, typeFilter, severityFilter, sortDirection]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    setCurrentPage(1);
  }, [typeFilter, severityFilter, searchQuery]);

  const visibleItems = searchQuery.trim()
    ? items.filter(
        (item) =>
          item.target.toLowerCase().includes(searchQuery.toLowerCase()) ||
          item.summary.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : items;

  const handleToggleSort = () => {
    setSortDirection((prev) => (prev === 'desc' ? 'asc' : 'desc'));
  };

  const handleConfirmDelete = async () => {
    if (!deleteTargetId) return;
    try {
      await deleteScanHistoryRecord(deleteTargetId);
      setDeleteTargetId(null);
      fetchHistory();
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Không thể xóa bản ghi này.');
      setDeleteTargetId(null);
    }
  };

  const handleViewDetails = (id: string) => {
    setDetailTargetId(id);
    setDetailRecord(null);
    setDetailError(null);
    setIsLoadingDetail(true);
    getScanHistoryRecord(id)
      .then((record) => setDetailRecord(record))
      .catch((err) => {
        setDetailError(err instanceof ApiError ? err.message : 'Không thể tải bản ghi này.');
      })
      .finally(() => setIsLoadingDetail(false));
  };

  const handleClearFilters = () => {
    setSearchQuery('');
    setTypeFilter('all');
    setSeverityFilter('all');
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <ToolkitLayout title="Lịch sử Kiểm tra" subtitle="Xem lại các lần kiểm tra website và tra cứu CVE trước đây.">
      <div className="space-y-6 font-mono text-xs">

        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-surface-container-highest/60 pb-5">

          <div className="flex-1 space-y-1.5 max-w-sm">
            <label className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold" htmlFor="history-search-input">
              Truy vấn đã ghi nhận
            </label>
            <div className="relative flex items-center bg-background border border-surface-container-highest focus-within:ring-1 focus-within:ring-primary/40 focus-within:border-primary/40 rounded-lg p-1.5 transition-all">
              <Search className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
              <input
                id="history-search-input"
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Tìm theo tiêu chí kiểm tra..."
                className="w-full bg-transparent border-none py-1 pl-8 text-xs text-text-primary placeholder:text-text-muted focus:outline-none"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="space-y-1">
              <span className="text-[8px] text-text-muted uppercase font-bold">Loại kiểm tra</span>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value as typeof typeFilter)}
                className="bg-background border border-surface-container-highest rounded-lg p-2 text-text-primary focus:outline-none"
              >
                <option value="all">TẤT CẢ LOẠI</option>
                <option value="url_scan">QUÉT URL</option>
                <option value="cve_lookup">TRA CỨU CVE</option>
              </select>
            </div>

            <div className="space-y-1">
              <span className="text-[8px] text-text-muted uppercase font-bold">Mức độ cảnh báo</span>
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value as typeof severityFilter)}
                className="bg-background border border-surface-container-highest rounded-lg p-2 text-text-primary focus:outline-none"
              >
                <option value="all">TẤT CẢ MỨC ĐỘ</option>
                <option value="critical">NGHIÊM TRỌNG</option>
                <option value="high">CAO</option>
                <option value="medium">TRUNG BÌNH</option>
                <option value="low">THẤP</option>
              </select>
            </div>

            {(searchQuery || typeFilter !== 'all' || severityFilter !== 'all') && (
              <button
                onClick={handleClearFilters}
                className="text-[9px] text-primary hover:underline mt-4 py-2 font-bold uppercase"
              >
                Đặt lại bộ lọc
              </button>
            )}
          </div>

        </div>

        {errorMsg && (
          <div className="bg-critical/10 border border-critical/30 text-critical text-xs p-3 rounded-lg flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        <div className="bg-background/20 border border-surface-container-highest rounded-lg overflow-hidden">

          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-container-low border-b border-surface-container-highest text-text-muted text-[9px] tracking-wider uppercase">
                  <th className="p-3">Loại kiểm tra</th>
                  <th className="p-3">Mục truy vấn</th>
                  <th className="p-3">Trạng thái</th>
                  <th className="p-3">Mức độ</th>
                  <th className="p-3">
                    <button onClick={handleToggleSort} className="flex items-center gap-1 hover:text-text-primary">
                      <span>Thời gian</span>
                      <ArrowUpDown className="h-3 w-3" />
                    </button>
                  </th>
                  <th className="p-3 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-highest/60 text-xs">
                {isLoading ? (
                  <tr>
                    <td colSpan={6} className="text-center py-10 text-text-muted italic">Đang tải lịch sử quét...</td>
                  </tr>
                ) : visibleItems.length > 0 ? (
                  visibleItems.map((item) => {
                    const isCrit = item.severity === 'critical';
                    const isHigh = item.severity === 'high';
                    return (
                      <tr key={item.id} className="hover:bg-background/30 transition-colors">
                        <td className="p-3 capitalize font-bold text-text-secondary">{SCAN_TYPE_LABEL[item.scan_type] ?? item.scan_type.replace('_', ' ')}</td>
                        <td className="p-3 truncate max-w-[200px]" title={item.target}>{item.target}</td>
                        <td className="p-3 text-text-muted">{item.summary}</td>
                        <td className="p-3">
                          {item.severity ? (
                            <span className={`px-1.5 py-0.2 rounded text-[8px] font-bold ${
                              isCrit ? 'bg-critical/10 text-critical border border-critical/15' :
                              isHigh ? 'bg-high/10 text-high border border-high/15' : 'bg-medium/10 text-medium border border-medium/15'
                            }`}>
                              {SEVERITY_LABEL[item.severity] ?? item.severity.toUpperCase()}
                            </span>
                          ) : (
                            <span className="text-text-muted">—</span>
                          )}
                        </td>
                        <td className="p-3 text-text-muted">{new Date(item.created_at).toLocaleString()}</td>
                        <td className="p-3 text-right">
                          <div className="flex justify-end items-center gap-1">
                            <button
                              onClick={() => handleViewDetails(item.id)}
                              className="p-1 text-text-secondary hover:text-primary hover:bg-surface-container-high rounded"
                              title="Xem chi tiết"
                            >
                              <Eye className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => setDeleteTargetId(item.id)}
                              className="p-1 text-text-secondary hover:text-critical hover:bg-surface-container-high rounded"
                              title="Xóa bản ghi"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={6} className="text-center py-10 text-text-muted italic">Không tìm thấy lịch sử truy vấn khớp với tiêu chí.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="sm:hidden divide-y divide-surface-container-highest/60">
            {visibleItems.length > 0 ? (
              visibleItems.map((item) => {
                const isCrit = item.severity === 'critical';
                const isHigh = item.severity === 'high';
                return (
                  <div key={item.id} className="p-4 space-y-3 hover:bg-background/20">
                    <div className="flex justify-between items-center">
                      <span className="capitalize font-bold text-text-primary text-xs">{SCAN_TYPE_LABEL[item.scan_type] ?? item.scan_type.replace('_', ' ')}</span>
                      {item.severity && (
                        <span className={`px-1.5 py-0.2 rounded text-[8px] font-bold ${
                          isCrit ? 'bg-critical/10 text-critical border border-critical/15' :
                          isHigh ? 'bg-high/10 text-high border border-high/15' : 'bg-medium/10 text-medium border border-medium/15'
                        }`}>
                          {SEVERITY_LABEL[item.severity] ?? item.severity.toUpperCase()}
                        </span>
                      )}
                    </div>
                    <div className="space-y-1 text-xs">
                      <div>
                        <span className="text-text-muted uppercase text-[9px] block">Truy vấn:</span>
                        <span className="text-text-secondary truncate block">{item.target}</span>
                      </div>
                      <div>
                        <span className="text-text-muted uppercase text-[9px] block">Chẩn đoán:</span>
                        <span className="text-text-secondary block leading-relaxed">{item.summary}</span>
                      </div>
                      <div>
                        <span className="text-text-muted uppercase text-[9px] block font-mono">Ngày:</span>
                        <span className="text-text-muted">{new Date(item.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                    <div className="flex justify-end gap-1 pt-2 border-t border-surface-container-highest/30">
                      <button
                        onClick={() => handleViewDetails(item.id)}
                        className="flex items-center gap-1.5 text-primary text-[10px] py-1 px-2 hover:bg-surface-container-high rounded"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        <span>XEM CHI TIẾT</span>
                      </button>
                      <button
                        onClick={() => setDeleteTargetId(item.id)}
                        className="flex items-center gap-1.5 text-critical text-[10px] py-1 px-2 hover:bg-surface-container-high rounded"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        <span>XÓA NHẬT KÝ</span>
                      </button>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-center py-10 text-text-muted italic">Không tìm thấy lịch sử truy vấn.</div>
            )}
          </div>

        </div>

        {totalPages > 1 && (
          <div className="flex justify-between items-center font-mono text-[10px] px-1">
            <span className="text-text-muted">TRANG {currentPage} / {totalPages}</span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setCurrentPage(Math.max(currentPage - 1, 1))}
                disabled={currentPage === 1}
                className="p-1 hover:bg-surface-container-high rounded disabled:opacity-30 text-text-secondary hover:text-text-primary"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={() => setCurrentPage(Math.min(currentPage + 1, totalPages))}
                disabled={currentPage === totalPages}
                className="p-1 hover:bg-surface-container-high rounded disabled:opacity-30 text-text-secondary hover:text-text-primary"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

      </div>

      {detailTargetId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4" aria-modal="true" role="dialog" aria-label="Chi tiết bản ghi quét">
          <div className="w-full max-w-lg bg-surface-container-high border border-surface-container-highest rounded-xl p-5 shadow-elevated space-y-4 max-h-[80vh] overflow-y-auto">
            <div className="flex items-start justify-between gap-3">
              <h3 className="font-headline font-bold text-sm text-text-primary">Chi tiết bản ghi quét</h3>
              <button
                onClick={() => setDetailTargetId(null)}
                className="p-1 text-text-secondary hover:text-text-primary hover:bg-surface-container-highest rounded"
                aria-label="Đóng"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {isLoadingDetail ? (
              <div className="flex flex-col items-center justify-center py-8 space-y-2 font-mono">
                <Loader2 className="h-6 w-6 text-primary animate-spin" />
                <span className="text-[10px] text-text-muted uppercase">Đang tải bản ghi...</span>
              </div>
            ) : detailError ? (
              <div className="flex flex-col items-center justify-center py-8 space-y-2 font-mono text-critical">
                <AlertTriangle className="h-6 w-6" />
                <span className="text-[10px] uppercase text-center">{detailError}</span>
                <button
                  onClick={() => detailTargetId && handleViewDetails(detailTargetId)}
                  className="text-[10px] text-primary hover:underline uppercase font-bold mt-1"
                >
                  Thử lại
                </button>
              </div>
            ) : detailRecord ? (
              <div className="space-y-4 text-xs">
                <dl className="grid grid-cols-2 gap-y-1.5 text-[11px]">
                  <dt className="text-text-muted uppercase tracking-widest font-bold">Loại</dt>
                  <dd className="text-text-secondary capitalize">{SCAN_TYPE_LABEL[detailRecord.scan_type] ?? detailRecord.scan_type.replace('_', ' ')}</dd>
                  <dt className="text-text-muted uppercase tracking-widest font-bold">Đối tượng</dt>
                  <dd className="text-text-secondary break-all">{detailRecord.target}</dd>
                  <dt className="text-text-muted uppercase tracking-widest font-bold">Trạng thái</dt>
                  <dd className="text-text-secondary capitalize">{detailRecord.status}</dd>
                  {detailRecord.severity && (
                    <>
                      <dt className="text-text-muted uppercase tracking-widest font-bold">Mức độ</dt>
                      <dd className="text-text-secondary uppercase">{detailRecord.severity}</dd>
                    </>
                  )}
                  <dt className="text-text-muted uppercase tracking-widest font-bold">Đã ghi nhận</dt>
                  <dd className="text-text-secondary">{new Date(detailRecord.created_at).toLocaleString()}</dd>
                </dl>
                <div className="border-t border-surface-container-highest/60 pt-3">
                  <ScanDetailsBody record={detailRecord} />
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {deleteTargetId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4" aria-modal="true" role="dialog" aria-label="Xác nhận xóa nhật ký">
          <div className="w-full max-w-sm bg-surface-container-high border border-surface-container-highest rounded-xl p-5 shadow-elevated space-y-4">

            <div className="flex items-start gap-3">
              <div className="h-10 w-10 rounded-full bg-critical/10 border border-critical/30 flex items-center justify-center text-critical shrink-0">
                <Trash2 className="h-5 w-5" />
              </div>
              <div className="space-y-1">
                <h3 className="font-headline font-bold text-sm text-text-primary">Xác nhận xóa nhật ký</h3>
                <p className="text-xs text-text-secondary leading-relaxed">
                  Bạn có chắc muốn xóa vĩnh viễn mục lịch sử quét này không?
                </p>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2 font-mono text-[10px]">
              <button
                onClick={() => setDeleteTargetId(null)}
                className="px-3.5 py-2 border border-surface-container-highest hover:bg-surface-container-high rounded-lg font-bold"
              >
                HỦY
              </button>
              <button
                onClick={handleConfirmDelete}
                className="px-3.5 py-2 bg-critical text-background hover:bg-critical-dim rounded-lg font-bold"
              >
                XÓA NHẬT KÝ
              </button>
            </div>

          </div>
        </div>
      )}

    </ToolkitLayout>
  );
};
export default ScanHistoryView;
