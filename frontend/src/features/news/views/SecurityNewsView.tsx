import React, { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AlertTriangle, ExternalLink, Inbox, RefreshCw, Search, Settings, Sparkles, Star } from 'lucide-react';
import { AuthContext } from '../../auth/AuthContext';
import {
  listSecurityNews,
  setSecurityNewsBookmark,
  type SecurityNewsArticle,
} from '../../../lib/api/securityNews';
import { ApiError } from '../../../lib/api/client';

const COMPOSER_DRAFT_KEY = 'cybersec_composer_draft';

type LoadState = 'loading' | 'success' | 'empty' | 'error';

export const SecurityNewsView: React.FC = () => {
  // useContext (not the throwing useAuth()) - the admin-only "manage
  // sources" link is an optional enhancement, not something this page's
  // core read-first feed should ever depend on hard-failing for.
  const auth = useContext(AuthContext);
  const navigate = useNavigate();
  const isAdmin = auth?.user?.role === 'admin' || auth?.user?.role === 'super_admin';

  const [items, setItems] = useState<SecurityNewsArticle[]>([]);
  const [search, setSearch] = useState('');
  const [bookmarkedOnly, setBookmarkedOnly] = useState(false);
  const [state, setState] = useState<LoadState>('loading');
  const [errorMsg, setErrorMsg] = useState('');
  const [isDegraded, setIsDegraded] = useState(false);
  // load() is memoized on [bookmarkedOnly, search] only, so a plain closure
  // over `items` would go stale between filter changes - a ref always reads
  // the latest value regardless of when this particular load() was created.
  const itemsRef = useRef<SecurityNewsArticle[]>([]);

  const load = useCallback(() => {
    setState('loading');
    setErrorMsg('');
    listSecurityNews({
      search: search.trim() || undefined,
      bookmarked: bookmarkedOnly ? true : undefined,
    })
      .then((page) => {
        itemsRef.current = page.items;
        setItems(page.items);
        setIsDegraded(false);
        setState(page.items.length === 0 ? 'empty' : 'success');
      })
      .catch((err) => {
        setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải Tin tức Bảo mật.');
        // A failed refresh should not blank out news the user already saw -
        // keep the last successfully loaded feed visible and mark it stale.
        if (itemsRef.current.length > 0) {
          setIsDegraded(true);
          setState('success');
        } else {
          setState('error');
        }
      });
  }, [bookmarkedOnly, search]);

  useEffect(load, [load]);

  const toggleBookmark = async (article: SecurityNewsArticle) => {
    try {
      const updated = await setSecurityNewsBookmark(article.id, !article.bookmarked);
      setItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch {
      // best-effort - a failed toggle just leaves the star as it was
    }
  };

  const handleAiExplain = (article: SecurityNewsArticle) => {
    const prompt = `Giải thích bài viết bảo mật sau và cho biết mức độ cần chú ý, ai nên quan tâm và nên làm gì:\n\nTiêu đề: ${article.title}\nNguồn: ${article.source}\nURL: ${article.url}\nTóm tắt: ${article.summary}`;
    try {
      sessionStorage.setItem(COMPOSER_DRAFT_KEY, prompt);
    } catch {
      // sessionStorage unavailable - AI Assistant just opens with an empty composer
    }
    navigate('/ai');
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Tin tức Bảo mật</h2>
          <p className="text-xs text-text-secondary">Cập nhật các thông tin và cảnh báo an toàn thông tin mới nhất.</p>
        </div>
        <button onClick={load} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-surface-container-highest text-xs shrink-0">
          <RefreshCw className="h-3.5 w-3.5" /> Làm mới
        </button>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <input
            aria-label="Tìm kiếm tin tức"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Tìm theo tiêu đề, tóm tắt, nguồn..."
            className="w-full pl-9 pr-3 py-2 bg-background border border-surface-container-highest rounded-lg text-xs"
          />
        </div>
        <label className="flex items-center gap-2 text-xs text-text-secondary">
          <input type="checkbox" checked={bookmarkedOnly} onChange={(e) => setBookmarkedOnly(e.target.checked)} />
          Chỉ hiện đã đánh dấu
        </label>
        {isAdmin && (
          <Link
            to="/admin/crawler"
            className="ml-auto flex items-center gap-1.5 px-3 py-2 rounded-lg border border-surface-container-highest text-xs text-text-secondary hover:text-primary hover:border-primary/30"
          >
            <Settings className="h-3.5 w-3.5" /> Quản lý nguồn tin
          </Link>
        )}
      </div>

      {isDegraded && (
        <div className="flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Không thể cập nhật một số nguồn tin. Đang hiển thị tin tức đã lưu gần nhất.
        </div>
      )}

      {state === 'loading' && (
        <div className="py-16 text-center text-xs text-text-muted">Đang tải tin tức...</div>
      )}

      {state === 'error' && (
        <div className="flex flex-col items-center gap-3 py-16 text-center border border-dashed border-critical/30 rounded-lg bg-critical/5">
          <AlertTriangle className="h-8 w-8 text-critical" />
          <p className="text-xs text-critical max-w-sm">{errorMsg}</p>
          <button onClick={load} className="px-3 py-1.5 rounded-lg bg-primary text-background text-xs font-bold">Thử tải lại</button>
        </div>
      )}

      {state === 'empty' && (
        <div className="flex flex-col items-center gap-3 py-16 text-center border border-dashed border-surface-container-highest rounded-lg">
          <Inbox className="h-8 w-8 text-text-muted opacity-50" />
          <div className="space-y-1">
            <p className="text-xs text-text-secondary font-bold">Chưa có tin tức bảo mật.</p>
            <p className="text-[11px] text-text-muted max-w-sm">Nguồn dữ liệu chưa được đồng bộ hoặc hiện chưa có bài viết.</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load} className="px-3 py-1.5 rounded-lg border border-surface-container-highest text-xs font-bold">Thử tải lại</button>
            {isAdmin && (
              <button
                onClick={() => navigate('/admin/crawler')}
                className="px-3 py-1.5 rounded-lg bg-primary text-background text-xs font-bold"
              >
                Quản lý nguồn tin
              </button>
            )}
          </div>
        </div>
      )}

      {state === 'success' && (
        <div className="space-y-3">
          {items.map((article) => (
            <article key={article.id} className="bg-surface-container border border-surface-container-highest rounded-lg p-4" data-testid={`news-card-${article.id}`}>
              <div className="flex items-start gap-3">
                <button
                  aria-label={article.bookmarked ? 'Bỏ đánh dấu' : 'Đánh dấu'}
                  onClick={() => toggleBookmark(article)}
                  className="mt-1 text-primary shrink-0"
                >
                  <Star className="h-4 w-4" fill={article.bookmarked ? 'currentColor' : 'none'} />
                </button>
                <div className="flex-1 min-w-0 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    {article.category && (
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase bg-primary/10 text-primary border border-primary/20">
                        {article.category}
                      </span>
                    )}
                    <p className="text-[10px] text-text-muted">{article.source} · {new Date(article.published_at).toLocaleString()}</p>
                  </div>
                  <Link to={`/news/${article.id}`} className="font-bold text-text-primary hover:text-primary block">{article.title}</Link>
                  <p className="text-xs text-text-secondary line-clamp-2">{article.summary}</p>
                  <div className="flex flex-wrap items-center gap-3 pt-1">
                    <Link to={`/news/${article.id}`} className="text-[10px] font-mono font-bold text-primary hover:underline">
                      ĐỌC CHI TIẾT
                    </Link>
                    <button
                      onClick={() => handleAiExplain(article)}
                      className="flex items-center gap-1 text-[10px] font-mono font-bold text-text-secondary hover:text-primary"
                    >
                      <Sparkles className="h-3 w-3" /> AI GIẢI THÍCH
                    </button>
                  </div>
                </div>
                <a href={article.url} target="_blank" rel="noreferrer" className="text-text-muted hover:text-primary shrink-0" title="Mở bài viết gốc">
                  <ExternalLink className="h-4 w-4" />
                </a>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
};

export default SecurityNewsView;
