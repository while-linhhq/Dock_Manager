import React from 'react';
import { FileText, Settings, Sparkles } from 'lucide-react';
import { cn } from '../../../utils/cn';

export type RevenueMainTab = 'invoices' | 'auto_invoices' | 'fees';

export type RevenueMainTabsProps = {
  activeTab: RevenueMainTab;
  onTabChange: (tab: RevenueMainTab) => void;
};

export const RevenueMainTabs: React.FC<RevenueMainTabsProps> = ({ activeTab, onTabChange }) => {
  return (
    <div className="flex space-x-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit">
      <button
        type="button"
        onClick={() => onTabChange('invoices')}
        className={cn(
          'px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2',
          activeTab === 'invoices'
            ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
            : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
        )}
      >
        <FileText className="w-4 h-4" />
        <span>Hóa Đơn</span>
      </button>
      <button
        type="button"
        onClick={() => onTabChange('auto_invoices')}
        className={cn(
          'px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2',
          activeTab === 'auto_invoices'
            ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
            : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
        )}
      >
        <Sparkles className="w-4 h-4" />
        <span>Hóa Đơn Tự Động</span>
      </button>
      <button
        type="button"
        onClick={() => onTabChange('fees')}
        className={cn(
          'px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2',
          activeTab === 'fees'
            ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
            : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
        )}
      >
        <Settings className="w-4 h-4" />
        <span>Cấu Hình Phí</span>
      </button>
    </div>
  );
};
