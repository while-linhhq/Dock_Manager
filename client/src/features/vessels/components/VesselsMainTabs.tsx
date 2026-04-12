import React from 'react';
import { Ship, Tag } from 'lucide-react';
import { cn } from '../../../utils/cn';

export type VesselsMainTab = 'vessels' | 'types';

export type VesselsMainTabsProps = {
  activeTab: VesselsMainTab;
  onTabChange: (tab: VesselsMainTab) => void;
};

export const VesselsMainTabs: React.FC<VesselsMainTabsProps> = ({ activeTab, onTabChange }) => {
  return (
    <div className="flex space-x-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit">
      <button
        type="button"
        onClick={() => onTabChange('vessels')}
        className={cn(
          'px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2',
          activeTab === 'vessels'
            ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
            : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
        )}
      >
        <Ship className="w-4 h-4" />
        <span>Danh Sách Tàu</span>
      </button>
      <button
        type="button"
        onClick={() => onTabChange('types')}
        className={cn(
          'px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2',
          activeTab === 'types'
            ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
            : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
        )}
      >
        <Tag className="w-4 h-4" />
        <span>Loại Tàu</span>
      </button>
    </div>
  );
};
