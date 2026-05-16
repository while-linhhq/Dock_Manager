import React from 'react';
import { Settings, Cpu, ShieldCheck, Anchor, CreditCard } from 'lucide-react';
import { cn } from '../../../utils/cn';

export type PortMainTab = 'detections' | 'configs' | 'payment' | 'pipeline' | 'seam-anchor';

const TABS: { id: PortMainTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'detections', label: 'Nhận Diện', icon: ShieldCheck },
  { id: 'configs', label: 'Cấu Hình', icon: Settings },
  { id: 'payment', label: 'Cấu Hình Thanh Toán', icon: CreditCard },
  { id: 'pipeline', label: 'AI Pipeline', icon: Cpu },
  { id: 'seam-anchor', label: 'Seam Anchor', icon: Anchor },
];

export type PortMainTabsProps = {
  activeTab: PortMainTab;
  onTabChange: (tab: PortMainTab) => void;
};

export const PortMainTabs: React.FC<PortMainTabsProps> = ({ activeTab, onTabChange }) => {
  return (
    <div className="flex space-x-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit overflow-x-auto">
      {TABS.map((tab) => {
        const Icon = tab.icon;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onTabChange(tab.id)}
            className={cn(
              'px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2 whitespace-nowrap',
              activeTab === tab.id
                ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
            )}
          >
            <Icon className="w-4 h-4" />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
};
