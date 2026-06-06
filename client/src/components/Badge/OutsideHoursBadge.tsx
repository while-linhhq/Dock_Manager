import React from 'react';
import { Moon } from 'lucide-react';
import { cn } from '../../utils/cn';

export type OutsideHoursBadgeProps = {
  className?: string;
};

export const OutsideHoursBadge: React.FC<OutsideHoursBadgeProps> = ({ className }) => {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border border-violet-500/30 bg-violet-500/10',
        'px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-violet-600 dark:text-violet-400',
        className,
      )}
      title="Tàu neo ngoài khung giờ hoạt động đã cấu hình"
    >
      <Moon className="h-3 w-3 shrink-0" />
      Ngoài giờ
    </span>
  );
};
