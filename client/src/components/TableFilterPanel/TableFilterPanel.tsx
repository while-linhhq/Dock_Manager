import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Filter, RotateCcw } from 'lucide-react';
import { Button } from '../Button/Button';
import { cn } from '../../utils/cn';

export const filterControlClass =
  'w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-[#121214] dark:text-white focus:border-blue-500 focus:ring-0';

type TableFilterPanelProps = {
  title?: string;
  defaultOpen?: boolean;
  onReset?: () => void;
  children: React.ReactNode;
  className?: string;
  activeCount?: number;
};

export function TableFilterPanel({
  title = 'Bộ lọc',
  defaultOpen = false,
  onReset,
  children,
  className,
  activeCount,
}: TableFilterPanelProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div
      className={cn(
        'rounded-2xl border border-gray-200 dark:border-white/5 bg-white dark:bg-[#121214] shadow-xl overflow-hidden',
        className,
      )}
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={cn(
          'w-full flex items-center justify-between px-4 py-3 text-left bg-gray-50 dark:bg-white/[0.02] hover:bg-gray-100/80 dark:hover:bg-white/[0.04] transition-colors',
          open && 'border-b border-gray-200 dark:border-white/5',
        )}
      >
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
          <Filter className="w-4 h-4 text-blue-500 shrink-0" />
          {title}
          {!open && (
            <span className="text-[9px] font-medium normal-case tracking-normal text-gray-400">
              — nhấn để mở
            </span>
          )}
          {activeCount != null && activeCount > 0 && (
            <span className="rounded-full bg-blue-600 text-white px-2 py-0.5 text-[9px] font-bold tabular-nums">
              {activeCount}
            </span>
          )}
        </span>
        {open ? (
          <ChevronUp className="w-4 h-4 text-gray-500 shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-500 shrink-0" />
        )}
      </button>
      {open && (
        <div className="p-4 md:p-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {children}
          </div>
          {onReset && (
            <div className="flex justify-end pt-2 border-t border-gray-100 dark:border-white/5">
              <Button type="button" variant="outline" size="sm" onClick={onReset}>
                <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                Xóa bộ lọc
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type FilterFieldProps = {
  label: string;
  children: React.ReactNode;
  className?: string;
};

export function FilterField({ label, children, className }: FilterFieldProps) {
  return (
    <div className={cn('space-y-1.5 min-w-0', className)}>
      <span className="block text-[10px] font-bold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
        {label}
      </span>
      {children}
    </div>
  );
}
