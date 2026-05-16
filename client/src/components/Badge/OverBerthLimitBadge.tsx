import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { cn } from '../../utils/cn';

export type OverBerthLimitBadgeProps = {
  className?: string;
};

export const OverBerthLimitBadge: React.FC<OverBerthLimitBadgeProps> = ({ className }) => {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border border-orange-500/30 bg-orange-500/10',
        'px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-orange-600 dark:text-orange-400',
        className,
      )}
      title="Tàu này đã vượt giới hạn neo đậu (theo mã tàu) trong kỳ đã cấu hình"
    >
      <AlertTriangle className="h-3 w-3 shrink-0" />
      Quá giới hạn
    </span>
  );
};
