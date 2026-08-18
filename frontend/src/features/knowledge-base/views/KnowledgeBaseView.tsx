import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  reprocessDocument,
  previewRetrieval,
} from '../../../lib/api/knowledge';
import type { KnowledgeDocument, RetrievedChunk } from '../../../lib/api/knowledge';
import { ApiError } from '../../../lib/api/client';
import { useEmbeddingReadiness } from '../../../hooks/useEmbeddingReadiness';
import {
  Upload, Trash2, RefreshCw, FileText, AlertTriangle, CheckCircle2, Clock, XCircle, Search, Loader2,
} from 'lucide-react';

const PAGE_SIZE = 20;

function StatusBadge({ status }: { status: KnowledgeDocument['processing_status'] }) {
  const config: Record<KnowledgeDocument['processing_status'], { label: string; className: string; icon: React.ReactNode }> = {
    ready: { label: 'SẴN SÀNG', className: 'bg-primary/10 text-primary border-primary/20', icon: <CheckCircle2 className="h-3 w-3" /> },
    processing: { label: 'ĐANG XỬ LÝ', className: 'bg-info/10 text-info border-info/20', icon: <Clock className="h-3 w-3 animate-spin" /> },
    pending: { label: 'CHỜ XỬ LÝ', className: 'bg-medium/10 text-medium border-medium/20', icon: <Clock className="h-3 w-3" /> },
    failed: { label: 'THẤT BẠI', className: 'bg-critical/10 text-critical border-critical/20', icon: <XCircle className="h-3 w-3" /> },
  };
  const { label, className, icon } = config[status];
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[8px] font-bold border ${className}`}>
      {icon}
      {label}
    </span>
  );
}

export const KnowledgeBaseView: React.FC = () => {
  const { documentId } = useParams<{ documentId?: string }>();
  const navigate = useNavigate();

  const [items, setItems] = useState<KnowledgeDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const embeddingReadiness = useEmbeddingReadiness();

  const [previewQuery, setPreviewQuery] = useState('');
  const [previewResults, setPreviewResults] = useState<RetrievedChunk[] | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const highlightRef = useRef<HTMLTableRowElement>(null);

  const fetchDocuments = useCallback(() => {
    setIsLoading(true);
    listDocuments(1, PAGE_SIZE)
      .then((page) => {
        setItems(page.items);
        setTotal(page.total);
        setErrorMsg(null);
      })
      .catch((err) => {
        setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải danh sách tài liệu.');
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    if (documentId && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [documentId, items]);

  // Poll while any document is still pending/processing, so status flips to
  // ready/failed without a manual refresh - ingestion in this phase runs
  // synchronously within the upload request, but a reprocess or a later
  // async pipeline could leave a document mid-flight.
  useEffect(() => {
    const hasInFlight = items.some((d) => d.processing_status === 'pending' || d.processing_status === 'processing');
    if (!hasInFlight) return;
    const timer = setInterval(fetchDocuments, 3000);
    return () => clearInterval(timer);
  }, [items, fetchDocuments]);

  const handleFileSelected = async (file: File) => {
    setIsUploading(true);
    setErrorMsg(null);
    try {
      await uploadDocument(file, uploadTitle.trim() || undefined);
      setUploadTitle('');
      fetchDocuments();
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải lên tài liệu này.');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTargetId) return;
    try {
      await deleteDocument(deleteTargetId);
      setDeleteTargetId(null);
      fetchDocuments();
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Không thể xóa tài liệu này.');
      setDeleteTargetId(null);
    }
  };

  const handleReprocess = async (id: string) => {
    try {
      await reprocessDocument(id);
      fetchDocuments();
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Không thể xử lý lại tài liệu này.');
    }
  };

  const handlePreview = async () => {
    if (!previewQuery.trim()) return;
    setIsPreviewing(true);
    try {
      const result = await previewRetrieval(previewQuery.trim());
      setPreviewResults(result.results);
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Xem trước truy xuất thất bại.');
    } finally {
      setIsPreviewing(false);
    }
  };

  return (
    <div className="space-y-6 font-mono text-xs">

      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-surface-container-highest/60 pb-5">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Knowledge Base</h2>
          <p className="text-xs text-text-secondary">
            Tải lên tài liệu tham khảo để phục vụ trả lời theo cơ chế Retrieval-Augmented. Chỉ bạn có thể xem tài liệu
            bạn tải lên; các tài liệu không có chủ sở hữu (hiển thị là "Hệ thống") được chia sẻ cho mọi người dùng.
          </p>
        </div>
      </div>

      {errorMsg && (
        <div className="bg-critical/10 border border-critical/30 text-critical text-xs p-3 rounded-lg flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Upload panel */}
      <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5 space-y-3">
        <span className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold block">
          Tải lên tài liệu (.txt, .md, .pdf có lớp văn bản)
        </span>
        {embeddingReadiness.status === 'warming' && (
          <div
            id="embedding-warming-banner"
            className="flex items-center gap-2 bg-info/10 border border-info/20 text-info text-[10px] px-3 py-2 rounded-lg"
          >
            <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
            <span>
              Đang khởi tạo mô hình AI lần đầu
              {embeddingReadiness.elapsedSeconds !== null ? ` (${Math.round(embeddingReadiness.elapsedSeconds)}s)` : ''}
              . Upload vẫn hoạt động nhưng có thể chậm hơn bình thường trong lúc này.
            </span>
          </div>
        )}
        {embeddingReadiness.status === 'failed' && (
          <div className="flex items-center gap-2 bg-critical/10 border border-critical/20 text-critical text-[10px] px-3 py-2 rounded-lg">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            <span>Không thể khởi tạo mô hình AI. Upload sẽ tự thử lại ở lần yêu cầu tiếp theo.</span>
          </div>
        )}
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={uploadTitle}
            onChange={(e) => setUploadTitle(e.target.value)}
            placeholder="Tiêu đề (tùy chọn)"
            className="flex-1 bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40"
          />
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
            onChange={(e) => e.target.files?.[0] && handleFileSelected(e.target.files[0])}
            disabled={isUploading}
            className="hidden"
            id="knowledge-upload-input"
          />
          <label
            htmlFor="knowledge-upload-input"
            className={`flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-bold text-[10px] cursor-pointer ${
              isUploading
                ? 'bg-surface-container-high text-text-muted cursor-not-allowed'
                : 'bg-primary text-background hover:bg-primary-dim'
            }`}
          >
            <Upload className="h-3.5 w-3.5" />
            {isUploading ? 'ĐANG TẢI LÊN...' : 'CHỌN TỆP'}
          </label>
        </div>
      </div>

      {/* Documents table */}
      <div className="bg-background/20 border border-surface-container-highest rounded-lg overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-surface-container-low border-b border-surface-container-highest text-text-muted text-[9px] tracking-wider uppercase">
              <th className="p-3">Tiêu đề</th>
              <th className="p-3">Chủ sở hữu</th>
              <th className="p-3">Trạng thái</th>
              <th className="p-3">Số đoạn</th>
              <th className="p-3">Ngày tải lên</th>
              <th className="p-3 text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-container-highest/60 text-xs">
            {isLoading ? (
              <tr>
                <td colSpan={6} className="text-center py-10 text-text-muted italic">Đang tải danh sách tài liệu...</td>
              </tr>
            ) : items.length > 0 ? (
              items.map((doc) => (
                <tr
                  key={doc.id}
                  ref={doc.id === documentId ? highlightRef : undefined}
                  className={`hover:bg-background/30 transition-colors ${doc.id === documentId ? 'bg-primary/5 ring-1 ring-inset ring-primary/30' : ''}`}
                >
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <FileText className="h-3.5 w-3.5 text-text-muted shrink-0" />
                      <span className="truncate max-w-[220px]" title={doc.title}>{doc.title}</span>
                    </div>
                    {doc.processing_status === 'failed' && doc.error_message && (
                      <span className="block text-critical text-[9px] mt-1">{doc.error_message}</span>
                    )}
                  </td>
                  <td className="p-3 text-text-muted">{doc.owner_user_id ? 'Bạn' : 'Hệ thống'}</td>
                  <td className="p-3"><StatusBadge status={doc.processing_status} /></td>
                  <td className="p-3 text-text-muted">{doc.chunk_count}</td>
                  <td className="p-3 text-text-muted">{new Date(doc.created_at).toLocaleString()}</td>
                  <td className="p-3">
                    <div className="flex justify-end items-center gap-1">
                      {doc.owner_user_id && (
                        <>
                          <button
                            onClick={() => handleReprocess(doc.id)}
                            className="p-1 text-text-secondary hover:text-primary hover:bg-surface-container-high rounded"
                            title="Xử lý lại (chia đoạn và tạo embedding lại)"
                          >
                            <RefreshCw className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => setDeleteTargetId(doc.id)}
                            className="p-1 text-text-secondary hover:text-critical hover:bg-surface-container-high rounded"
                            title="Xóa tài liệu"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="text-center py-10 text-text-muted italic">Chưa có tài liệu nào được tải lên.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {total > 0 && <div className="text-[10px] text-text-muted">{total} tài liệu</div>}

      {/* Retrieval preview */}
      <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5 space-y-3">
        <span className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold block">
          Xem trước truy xuất
        </span>
        <div className="flex gap-2">
          <div className="relative flex-1 flex items-center">
            <Search className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
            <input
              type="text"
              value={previewQuery}
              onChange={(e) => setPreviewQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handlePreview()}
              placeholder="Nhập câu hỏi để xem chatbot sẽ truy xuất được gì..."
              className="w-full bg-background border border-surface-container-highest rounded-lg pl-9 pr-3 py-2 text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
          </div>
          <button
            onClick={handlePreview}
            disabled={isPreviewing || !previewQuery.trim()}
            className="px-4 py-2 bg-primary text-background rounded-lg font-bold text-[10px] disabled:opacity-40"
          >
            {isPreviewing ? 'ĐANG TÌM KIẾM...' : 'XEM TRƯỚC'}
          </button>
        </div>
        {previewResults !== null && (
          <div className="space-y-2 pt-2">
            {previewResults.length === 0 ? (
              <p className="text-text-muted italic">Không tìm thấy nội dung phù hợp trong Knowledge Base.</p>
            ) : (
              previewResults.map((chunk) => (
                <div
                  key={chunk.chunk_id}
                  className="bg-background border border-surface-container-highest rounded-lg p-3 space-y-1 cursor-pointer hover:border-primary/40"
                  onClick={() => navigate(`/knowledge-base/documents/${chunk.document_id}`)}
                >
                  <div className="flex items-center justify-between text-[9px] text-text-muted">
                    <span className="font-bold text-text-secondary">
                      {chunk.document_title}
                      {chunk.page ? ` · p.${chunk.page}` : ''}
                      {chunk.heading ? ` · ${chunk.heading}` : ''}
                    </span>
                    <span>{(chunk.score * 100).toFixed(0)}% khớp</span>
                  </div>
                  <p className="text-text-secondary leading-relaxed line-clamp-3">{chunk.content}</p>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {deleteTargetId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4" aria-modal="true" role="dialog" aria-label="Xác nhận xóa tài liệu">
          <div className="w-full max-w-sm bg-surface-container-high border border-surface-container-highest rounded-xl p-5 shadow-elevated space-y-4">
            <div className="flex items-start gap-3">
              <div className="h-10 w-10 rounded-full bg-critical/10 border border-critical/30 flex items-center justify-center text-critical shrink-0">
                <Trash2 className="h-5 w-5" />
              </div>
              <div className="space-y-1">
                <h3 className="font-headline font-bold text-sm text-text-primary">Xác nhận xóa tài liệu</h3>
                <p className="text-xs text-text-secondary leading-relaxed">
                  Thao tác này sẽ xóa vĩnh viễn tài liệu và toàn bộ các đoạn của nó. Tài liệu sẽ không còn
                  được chatbot truy xuất nữa.
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
                XÓA
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
export default KnowledgeBaseView;
