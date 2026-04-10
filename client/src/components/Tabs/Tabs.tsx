import React from 'react';
import { cn } from '../../utils/cn';

interface TabsProps {
  tabs: Array<{ id: string; label: string; icon?: React.ElementType }>;
  activeTab: string;
  onChange: (id: string) => void;
  className?: string;
}

export const Tabs: React.FC<TabsProps> = ({ tabs, activeTab, onChange, className }) => {
  return (
    <div className={cn("flex space-x-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit overflow-x-auto", className)}>
      {tabs.map((tab) => {
        const Icon = tab.icon;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={cn(
              "px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2 whitespace-nowrap",
              activeTab === tab.id 
                ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm" 
                : "text-gray-500 hover:text-gray-900 dark:hover:text-white"
            )}
          >
            {Icon && <Icon className="w-4 h-4" />}
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
};
