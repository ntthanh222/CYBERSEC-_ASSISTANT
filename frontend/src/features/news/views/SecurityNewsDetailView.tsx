import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, ExternalLink, Star } from 'lucide-react';
import {
  getSecurityNews,
  setSecurityNewsBookmark,
  setSecurityNewsRead,
  type SecurityNewsArticle,
} from '../../../lib/api/securityNews';

export const SecurityNewsDetailView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [article, setArticle] = useState<SecurityNewsArticle | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    setError('');
    getSecurityNews(id)
      .then(async (item) => {
        setArticle(item);
        if (!item.read) setArticle(await setSecurityNewsRead(item.id, true));
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Không tìm thấy bài viết.'));
  }, [id]);

  const toggleBookmark = async () => {
    if (!article) return;
    setArticle(await setSecurityNewsBookmark(article.id, !article.bookmarked));
  };

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-lg">
        <AlertTriangle className="h-10 w-10 opacity-40 text-critical" />
        <p className="text-xs">{error}</p>
        <Link to="/news" className="text-primary text-xs hover:underline">Quay lại Security News</Link>
      </div>
    );
  }
  if (!article) return <div className="py-20 text-center text-xs text-text-muted">Đang tải bài viết...</div>;

  return (
    <div className="space-y-6">
      <Link to="/news" className="flex items-center gap-1.5 text-text-muted hover:text-primary text-xs font-mono">
        <ArrowLeft className="h-3.5 w-3.5" /> Quay lại Security News
      </Link>
      <article className="bg-surface-container border border-surface-container-highest rounded-lg p-6 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs text-text-muted">{article.source} - {new Date(article.published_at).toLocaleString()}</p>
            <h2 className="font-headline font-black text-2xl text-text-primary mt-1">{article.title}</h2>
          </div>
          <button onClick={toggleBookmark} className="text-primary"><Star className="h-5 w-5" fill={article.bookmarked ? 'currentColor' : 'none'} /></button>
        </div>
        <p className="text-sm text-text-secondary leading-relaxed">{article.summary}</p>
        {article.ai_summary && (
          <div className="bg-background border border-surface-container-highest rounded p-3">
            <h3 className="text-[10px] font-mono text-text-muted uppercase font-bold mb-2">Tóm tắt AI đã lưu</h3>
            <p className="text-xs text-text-secondary">{article.ai_summary}</p>
          </div>
        )}
        {article.related_cves.length > 0 && <p className="text-xs text-text-muted">CVE liên quan: {article.related_cves.join(', ')}</p>}
        <a href={article.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-primary text-xs font-bold"><ExternalLink className="h-3.5 w-3.5" /> Mở bài viết gốc</a>
      </article>
    </div>
  );
};

export default SecurityNewsDetailView;
