import React from 'react';
import { cn } from '../../../utils/cn';

export function StatisticsLogTh({
  children,
  className,
  title,
}: {
  children: React.ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <th
      title={title}
      className={cn(
        'px-4 py-3.5 text-left align-bottom text-xs sm:text-sm font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wide border-b border-gray-200 dark:border-white/5 bg-gray-50 dark:bg-white/[0.02] whitespace-nowrap',
        className,
      )}
    >
      {children}
    </th>
  );
}

export function StatisticsLogTd({
  children,
  className,
  mono,
}: {
  children: React.ReactNode;
  className?: string;
  mono?: boolean;
}) {
  return (
    <td
      className={cn(
        'px-4 py-3 text-sm text-gray-800 dark:text-gray-200 border-b border-gray-100 dark:border-white/5 align-top',
        mono && 'font-mono text-xs sm:text-sm',
        className,
      )}
    >
      {children}
    </td>
  );
}
