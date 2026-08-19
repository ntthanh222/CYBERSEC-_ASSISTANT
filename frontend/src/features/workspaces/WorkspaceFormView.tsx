import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { createWorkspace, getWorkspace, updateWorkspace } from '../../lib/api/workspaces';
import { ApiError } from '../../lib/api/client';

export const WorkspaceFormView: React.FC = () => {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(id);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(isEditing);

  useEffect(() => {
    if (!id) return;
    getWorkspace(id)
      .then((workspace) => {
        setName(workspace.name);
        setDescription(workspace.description ?? '');
      })
      .catch((err) => setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải workspace.'))
      .finally(() => setIsLoading(false));
  }, [id]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      if (id) {
        await updateWorkspace(id, { name, description: description || null });
        navigate(`/workspaces/${id}`);
      } else {
        const created = await createWorkspace({ name, description: description || null });
        navigate(`/workspaces/${created.id}`);
      }
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Không thể lưu workspace.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return <p className="text-xs text-text-muted font-mono">Đang tải...</p>;
  }

  return (
    <div className="max-w-lg space-y-6">
      <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">
        {isEditing ? 'Chỉnh sửa Workspace' : 'Tạo Workspace mới'}
      </h2>

      <form onSubmit={handleSubmit} className="space-y-4" data-testid="workspace-form">
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">Tên</label>
          <input
            type="text"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
          />
        </div>
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">Mô tả</label>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            className="w-full bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
          />
        </div>

        {errorMsg && <p className="text-xs text-critical">{errorMsg}</p>}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={isSubmitting}
            className="px-4 py-2 bg-primary text-background rounded-lg text-xs font-mono font-bold hover:bg-primary-container transition-all disabled:opacity-40"
          >
            {isSubmitting ? 'ĐANG LƯU...' : 'LƯU'}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-4 py-2 border border-surface-container-highest rounded-lg text-xs font-mono font-bold text-text-secondary hover:text-text-primary"
          >
            HỦY
          </button>
        </div>
      </form>
    </div>
  );
};

export default WorkspaceFormView;
