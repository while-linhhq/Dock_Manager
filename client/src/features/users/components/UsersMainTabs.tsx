import React from 'react';
import { Shield, Users } from 'lucide-react';
import { cn } from '../../../utils/cn';

export type UsersMainTab = 'users' | 'roles';

export type UsersMainTabsProps = {
  activeTab: UsersMainTab;
  onTabChange: (tab: UsersMainTab) => void;
};

export const UsersMainTabs: React.FC<UsersMainTabsProps> = ({ activeTab, onTabChange }) => {
  return (
    <div className="flex space-x-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit">
      <button
        type="button"
        onClick={() => onTabChange('users')}
        className={cn(
          'px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2',
          activeTab === 'users'
            ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
            : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
        )}
      >
        <Users className="w-4 h-4" />
        <span>Người Dùng</span>
      </button>
      <button
        type="button"
        onClick={() => onTabChange('roles')}
        className={cn(
          'px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2',
          activeTab === 'roles'
            ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
            : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
        )}
      >
        <Shield className="w-4 h-4" />
        <span>Vai Trò</span>
      </button>
    </div>
  );
};
