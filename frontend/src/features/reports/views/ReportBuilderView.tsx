import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ArrowLeft } from 'lucide-react';
import { createReport, listReportTemplates, type ReportCategory, type ReportFormat, type ReportTemplate } from '../../../lib/api/reports';

export const ReportBuilderView: React.FC = () => {
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [error, setError] = useState('');
  const [createdId, setCreatedId] = useState('');
  const [form, setForm] = useState({
    title: '',
    category: 'executive' as ReportCategory,
    format: 'markdown' as ReportFormat,
    sections: 'Tóm tắt điều hành, Rủi ro chính',
    scope: '',
  });

  useEffect(() => {
    listReportTemplates()
      .then(setTemplates)
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải mẫu báo cáo.'));
  }, []);

  const applyTemplate = (template: ReportTemplate) => {
    setForm({
      title: template.title,
      category: template.category,
      format: 'markdown',
      sections: template.sections.join(', '),
      scope: template.description,
    });
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    const report = await createReport({
      title: form.title,
      category: form.category,
      format: form.format,
      sections: form.sections.split(',').map((item) => item.trim()).filter(Boolean),
      scope: form.scope,
    });
    setCreatedId(report.id);
  };

  return (
    <div className="space-y-6">
      <Link to="/reports" className="flex items-center gap-1.5 text-text-muted hover:text-primary text-xs font-mono">
        <ArrowLeft className="h-3.5 w-3.5" /> Quay lại Reports Center
      </Link>
      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Tạo báo cáo tùy chỉnh</h2>
        <p className="text-xs text-text-secondary">Tạo nội dung báo cáo Markdown hoặc CSV từ dữ liệu chuyên viên phân tích nhập vào.</p>
      </div>

      {error && <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical"><AlertTriangle className="h-4 w-4" />{error}</div>}
      {createdId && <div className="rounded-lg border border-success/30 bg-success/10 p-3 text-xs text-success">Báo cáo đã được tạo và lưu.</div>}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="space-y-3 xl:col-span-1">
          <h3 className="text-xs font-mono uppercase text-text-muted font-bold">Mẫu báo cáo</h3>
          {templates.map((template) => (
            <button key={template.id} onClick={() => applyTemplate(template)} className="w-full text-left bg-surface-container border border-surface-container-highest rounded-lg p-3" data-testid={`report-template-${template.id}`}>
              <span className="block text-sm font-bold text-text-primary">{template.title}</span>
              <span className="block text-xs text-text-muted mt-1">{template.description}</span>
            </button>
          ))}
        </section>
        <form onSubmit={submit} className="space-y-3 xl:col-span-2 bg-surface-container border border-surface-container-highest rounded-lg p-4">
          <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Tiêu đề báo cáo" className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as ReportCategory })} className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
              <option value="executive">Điều hành</option>
              <option value="technical">Kỹ thuật</option>
              <option value="compliance">Tuân thủ</option>
              <option value="incident">Sự cố</option>
            </select>
            <select value={form.format} onChange={(e) => setForm({ ...form, format: e.target.value as ReportFormat })} className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
              <option value="pdf">PDF</option>
              <option value="docx">Word/DOCX</option>
              <option value="csv">CSV</option>
              <option value="markdown">Markdown</option>
            </select>
          </div>
          <input value={form.sections} onChange={(e) => setForm({ ...form, sections: e.target.value })} placeholder="Các mục, cách nhau bởi dấu phẩy" className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
          <textarea value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })} placeholder="Phạm vi / ghi chú của chuyên viên phân tích" className="w-full min-h-32 bg-background border border-surface-container-highest rounded p-3 text-xs" />
          <button className="bg-primary text-background rounded px-4 py-2 text-xs font-bold">Tạo báo cáo</button>
        </form>
      </div>
    </div>
  );
};

export default ReportBuilderView;
