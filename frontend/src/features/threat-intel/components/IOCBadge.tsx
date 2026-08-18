import React from 'react';
import { Globe, Wifi, Hash, Link } from 'lucide-react';
import type { IOCType } from '../../../lib/api/threatIntel';

interface IOCBadgeProps {
  type: IOCType;
  className?: string;
}

const TYPE_CONFIG: Record<IOCType, { label: string; color: string; Icon: React.ElementType }> = {
  ip: { label: 'IP', color: 'bg-critical/10 text-critical border-critical/20', Icon: Wifi },
  domain: { label: 'DOMAIN', color: 'bg-high/10 text-high border-high/20', Icon: Globe },
  url: { label: 'URL', color: 'bg-warning/10 text-warning border-warning/20', Icon: Link },
  sha256: { label: 'SHA256', color: 'bg-primary/10 text-primary border-primary/20', Icon: Hash },
};

export const IOCBadge: React.FC<IOCBadgeProps> = ({ type, className = '' }) => {
  const config = TYPE_CONFIG[type] ?? TYPE_CONFIG.ip;
  const { label, color, Icon } = config;
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold font-mono border ${color} ${className}`}>
      <Icon className="h-2.5 w-2.5" />
      {label}
    </span>
  );
};

export default IOCBadge;
