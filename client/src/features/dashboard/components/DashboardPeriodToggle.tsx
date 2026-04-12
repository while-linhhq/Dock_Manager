import React from 'react';
import { cn } from '../../../utils/cn';
import type { DashboardPeriod } from '../../../types/api.types';

const OPTIONS: { id: DashboardPeriod; label: string }[] = [
  { id: 'day', label: 'Ngày' },
  { id: 'month', label: 'Tháng' },
  { id: 'year', label: 'Năm' },
];

export type DashboardPeriodToggleProps = {
  value: DashboardPeriod;
  onChange: (p: DashboardPeriod) => void;
  className?: string;
};

export const DashboardPeriodToggle: React.FC<DashboardPeriodToggleProps> = ({
  value,
  onChange,
  className,
}) => {
  return (
    <div
      className={cn(
        'inline-flex rounded-xl bg-gray-100 dark:bg-white/10 p-1 gap-0.5',
        className,
      )}
      role="group"
      aria-label="Chọn kỳ thống kê"
    >
      {OPTIONS.map((opt) => (
        <button
          key={opt.id}
          type="button"
          onClick={() => onChange(opt.id)}
          className={cn(
            'px-4 py-2 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all',
            value === opt.id
              ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
              : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
};
