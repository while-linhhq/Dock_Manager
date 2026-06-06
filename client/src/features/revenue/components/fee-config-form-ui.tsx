import React from 'react';
import { cn } from '../../../utils/cn';

export const feeLabelClass =
  'text-[10px] font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400';

export const feeControlClass =
  'h-8 w-full min-w-0 rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 transition-colors placeholder:text-gray-400 focus:border-blue-500 focus:outline-none dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-gray-500';

export const feeMonoControlClass = cn(feeControlClass, 'font-mono tabular-nums');

export const feeSectionClass =
  'space-y-2.5 rounded-xl border border-gray-200 bg-gray-50/60 p-3 dark:border-white/10 dark:bg-white/[0.03]';

export const feeSectionTitleClass = feeLabelClass;

export const feeErrorClass =
  'text-[10px] font-bold uppercase tracking-tighter text-red-500';

type FeeFieldProps = {
  label: string;
  error?: string;
  className?: string;
  children: React.ReactNode;
};

export function FeeField({ label, error, className, children }: FeeFieldProps) {
  return (
    <div className={cn('space-y-1', className)}>
      <span className={cn(feeLabelClass, 'block')}>{label}</span>
      {children}
      {error ? <p className={feeErrorClass}>{error}</p> : null}
    </div>
  );
}

type FeeSectionProps = {
  title: string;
  children: React.ReactNode;
  className?: string;
};

export function FeeSection({ title, children, className }: FeeSectionProps) {
  return (
    <section className={cn(feeSectionClass, className)}>
      <h4 className={feeSectionTitleClass}>{title}</h4>
      {children}
    </section>
  );
}
