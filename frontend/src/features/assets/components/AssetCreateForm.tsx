import React, { useEffect, useRef, useState } from 'react';
import { X, Loader2 } from 'lucide-react';
import { createAsset } from '../../../lib/api/assets';
import type { AssetType, BusinessCriticality } from '../../../lib/api/assets';
import { ApiError } from '../../../lib/api/client';

interface AssetCreateFormProps {
  onClose: () => void;
  onCreated: () => void;
}

const TYPE_OPTIONS: AssetType[] = ['server', 'workstation', 'cloud_resource', 'database', 'network_device'];
const CRITICALITY_OPTIONS: BusinessCriticality[] = ['low', 'medium', 'high', 'critical'];

const TYPE_LABEL: Record<AssetType, string> = {
  server: 'MÁY CHỦ',
  workstation: 'MÁY TRẠM',
  cloud_resource: 'TÀI NGUYÊN CLOUD',
  database: 'CƠ SỞ DỮ LIỆU',
  network_device: 'THIẾT BỊ MẠNG',
};

const CRITICALITY_LABEL: Record<BusinessCriticality, string> = {
  low: 'THẤP',
  medium: 'TRUNG BÌNH',
  high: 'CAO',
  critical: 'NGHIÊM TRỌNG',
};

export const AssetCreateForm: React.FC<AssetCreateFormProps> = ({ onClose, onCreated }) => {
  const firstInputRef = useRef<HTMLInputElement>(null);

  const [name, setName] = useState('');
  const [type, setType] = useState<AssetType>('server');
  const [hostname, setHostname] = useState('');
  const [ipAddress, setIpAddress] = useState('');
  const [operatingSystem, setOperatingSystem] = useState('');
  const [owner, setOwner] = useState('');
  const [department, setDepartment] = useState('');
  const [businessCriticality, setBusinessCriticality] = useState<BusinessCriticality>('medium');
  const [internetExposed, setInternetExposed] = useState(false);
  const [description, setDescription] = useState('');
  const [linkedCvesInput, setLinkedCvesInput] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    firstInputRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg(null);
    const linked_cves = linkedCvesInput
      .split(',')
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);

    createAsset({
      name,
      type,
      hostname,
      ip_address: ipAddress,
      operating_system: operatingSystem,
      owner,
      department,
      business_criticality: businessCriticality,
      internet_exposed: internetExposed,
      description,
      linked_cves,
    })
      .then(() => {
        onCreated();
      })
      .catch((err) => {
        setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tạo tài sản.');
      })
      .finally(() => setIsSubmitting(false));
  };

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-40 transition-opacity"
        onClick={onClose}
        data-testid="asset-create-overlay"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="asset-create-title"
        className="fixed top-0 right-0 h-full w-full max-w-md bg-background border-l border-surface-container-highest z-50 overflow-y-auto shadow-2xl"
        data-testid="asset-create-form"
      >
        <div className="sticky top-0 bg-background border-b border-surface-container-highest/60 p-5 flex items-start justify-between gap-4">
          <h3 id="asset-create-title" className="font-headline font-black text-lg text-text-primary">
            Thêm Tài sản
          </h3>
          <button
            onClick={onClose}
            aria-label="Đóng"
            className="p-1.5 rounded-lg border border-surface-container-highest text-text-muted hover:text-text-primary hover:bg-surface-container-high transition-all"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <label className="block space-y-1">
            <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Tên *</span>
            <input
              ref={firstInputRef}
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-surface-container border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Loại *</span>
            <select
              value={type}
              onChange={(e) => setType(e.target.value as AssetType)}
              className="w-full bg-surface-container border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
            >
              {TYPE_OPTIONS.map((t) => (
                <option key={t} value={t}>{TYPE_LABEL[t]}</option>
              ))}
            </select>
          </label>

          <label className="block space-y-1">
            <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Tên máy chủ *</span>
            <input
              required
              value={hostname}
              onChange={(e) => setHostname(e.target.value)}
              className="w-full bg-surface-container border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Địa chỉ IP *</span>
            <input
              required
              value={ipAddress}
              onChange={(e) => setIpAddress(e.target.value)}
              className="w-full bg-surface-container border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Hệ điều hành *</span>
            <input
              required
              value={operatingSystem}
              onChange={(e) => setOperatingSystem(e.target.value)}
              className="w-full bg-surface-container border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block space-y-1">
              <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Chủ sở hữu *</span>
              <input
                required
                value={owner}
                onChange={(e) => setOwner(e.target.value)}
                className="w-full bg-surface-container border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Phòng ban *</span>
              <input
                required
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="w-full bg-surface-container border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
              />
            </label>
          </div>

          <label className="block space-y-1">
            <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Mức độ quan trọng nghiệp vụ *</span>
            <select
              value={businessCriticality}
              onChange={(e) => setBusinessCriticality(e.target.value as BusinessCriticality)}
              className="w-full bg-surface-container border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
            >
              {CRITICALITY_OPTIONS.map((c) => (
                <option key={c} value={c}>{CRITICALITY_LABEL[c]}</option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-xs text-text-primary">
            <input
              type="checkbox"
              checked={internetExposed}
              onChange={(e) => setInternetExposed(e.target.checked)}
              className="h-4 w-4"
            />
            Có thể truy cập từ Internet
          </label>

          <label className="block space-y-1">
            <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Mô tả</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full bg-surface-container border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
          </label>

          <label className="block space-y-1">
            <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest">ID CVE liên kết (phân cách bằng dấu phẩy)</span>
            <input
              value={linkedCvesInput}
              onChange={(e) => setLinkedCvesInput(e.target.value)}
              placeholder="CVE-2021-44228, CVE-2023-22809"
              className="w-full bg-surface-container border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
          </label>

          {errorMsg && (
            <p className="text-xs text-critical" role="alert" data-testid="asset-create-error">
              {errorMsg}
            </p>
          )}

          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-primary text-background hover:bg-primary-container disabled:opacity-50 rounded-lg text-xs font-mono font-bold transition-all"
              data-testid="asset-create-submit"
            >
              {isSubmitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {isSubmitting ? 'ĐANG TẠO...' : 'TẠO TÀI SẢN'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-2 border border-surface-container-highest text-text-secondary hover:text-text-primary rounded-lg text-xs font-mono font-bold transition-all"
            >
              HỦY
            </button>
          </div>
        </form>
      </div>
    </>
  );
};

export default AssetCreateForm;
