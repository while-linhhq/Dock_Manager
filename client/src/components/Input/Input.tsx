import React from 'react';
import { cn } from '../../utils/cn';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  icon?: React.ElementType;
  error?: string;
}

export const Input: React.FC<InputProps> = ({ label, icon: Icon, error, className, ...props }) => {
  return (
    <div className="space-y-1">
      {label && <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">{label}</label>}
      <div className="relative">
        {Icon && <Icon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />}
        <input
          className={cn(
            "w-full py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all",
            Icon ? "pl-10 pr-4" : "px-4",
            error && "border-red-500 focus:border-red-500",
            className
          )}
          {...props}
        />
      </div>
      {error && <p className="text-[10px] text-red-500 font-bold uppercase tracking-tighter ml-1">{error}</p>}
    </div>
  );
};
